"""
Convert an EQUELLA item into an Invenio record.

Eventually this will accept a _directory_ containing the item's JSON and its
attachments, but for staters we are taking just JSON.
"""

from datetime import date
import json
import mimetypes
import re
import sys
from typing import Any, List

import xmltodict

from names import parse_name
from maps import *
from utils import find_items, mklist, to_edtf
from subjects import find_subjects, Subject


def postprocessor(path, key, value):
    """XML postprocessor, ensure that empty XML nodes like <foo></foo> are empty
    dicts, not None, so we can continue chaining .get() calls on the result."""
    # ? is this actually helpful? It's creating problems in places like with
    # ? publisher <originInfo><publisher/></originInfo> b/c publisher would
    # ? otherwise always be a string but now is a dict or str
    if value is None:
        return (key, {})
    return (key, value)


class Record:
    def __init__(self, item):
        self.xml = xmltodict.parse(item["metadata"], postprocessor=postprocessor)["xml"]
        # TODO attachments or is that mostly work in api.py?
        self.files = [a for a in item.get("attachments", []) if a["type"] == "file"]
        self.title = item.get("name", "Untitled")
        # default to current date in ISO 8601 format
        self.dateCreated = item.get("dateCreated", date.today().isoformat())
        if item.get("uuid") and item.get("version"):
            self.vault_url = (
                f"https://vault.cca.edu/items/{item['uuid']}/{item['version']}/"
            )
        else:
            self.vault_url = None

    @property
    def abstracts(self) -> list:
        abs = mklist(self.xml.get("mods", {}).get("abstract", ""))
        # filter out all empty strings except the first one
        for idx, a in enumerate(abs):
            if idx > 0 and not a:
                abs.remove(a)
        return abs

    @property
    def addl_titles(self) -> list[dict[str, str]]:
        # extra /mods/titleInfo/title entries, titleInfo/subtitle
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-titles-0-n
        # Types: https://127.0.0.1:5000/api/vocabularies/titletypes
        # alternative-title, other, subtitle, translated-title
        atitles = []
        titleinfos = mklist(self.xml.get("mods", {}).get("titleInfo"))
        for idx, titleinfo in enumerate(titleinfos):
            # all subtitles
            for subtitle in mklist(titleinfo.get("subTitle")):
                atitles.append({"title": subtitle, "type": {"id": "subtitle"}})
            # titles other than the first
            for title in mklist(titleinfo.get("title")):
                if idx > 0:
                    atype = titleinfo.get("@type")
                    if atype == "alternative":
                        atitles.append(
                            {"title": title, "type": {"id": "alternative-title"}}
                        )
                    elif atype == "translated":
                        atitles.append(
                            {"title": title, "type": {"id": "translated-title"}}
                        )
                    else:
                        atitles.append({"title": title, "type": {"id": "other"}})
        return atitles

    @property
    def creators(self) -> list[dict[str, Any]]:
        # mods/name
        # https://inveniordm.docs.cern.ch/reference/metadata/#creators-1-n
        namesx = mklist(self.xml.get("mods", {}).get("name"))
        creators = []
        for namex in namesx:
            # @usage = primary, secondary | ignoring this but could say sec. -> contributor, not creator
            partsx = namex.get("namePart")
            if type(partsx) == str:
                # initialize, use affiliation set to dedupe them
                creator = {"person_or_org": {}, "affiliations": [], "role": {}}

                # Role: creators can only have one role, take the first one
                rolex = mklist(namex.get("role", {}).get("roleTerm"))
                if len(rolex):
                    rolex = rolex[0]
                    role: str = rolex if type(rolex) == str else rolex.get("#text")
                    role = role.lower().replace(" ", "")
                    if role in role_map:
                        creator["role"]["id"] = role_map[role]
                    else:
                        creator["role"]["id"] = role

                # Affiliations
                affs = []
                subnamesx = mklist(namex.get("subNameWrapper"))
                for subnamex in subnamesx:
                    if subnamex.get("ccaAffiliated") == "Yes":
                        affs.append({"id": "01mmcf932"})
                    elif subnamex.get("affiliation"):
                        affsx = mklist(subnamex.get("affiliation"))
                        # skip our false positives of ccaAffiliated: No | affiliation: CCA
                        for affx in affsx:
                            if (
                                affx
                                and not re.match(r"CCA/?C?", affx, flags=re.IGNORECASE)
                                and not re.match(
                                    r"California College of (the)? Arts (and Crafts)?",
                                    affx,
                                    flags=re.IGNORECASE,
                                )
                            ):
                                affs.append({"name": affx})
                # dedupe list of dictionaries
                creator["affiliations"] = list(
                    {frozenset(d.items()): d for d in affs}.values()
                )

                names = parse_name(partsx)
                if type(names) == dict:
                    creators.append(
                        {
                            "person_or_org": names,
                            "role": creator["role"],
                            "affiliations": creator["affiliations"],
                        }
                    )
                # implies type(names) == list, similar to below, if parse_name returns a
                # list of names but we have role/affiliation then something is wrong
                elif creator.get("role") or len(creator.get("affiliation", [])):
                    raise Exception(
                        f"Unexpected mods/name structure: parse_name(namePart) returned a list but we also have role/affiliation. Name: {namex}"
                    )
                elif type(names) == list:
                    for name in names:
                        creators.append({"person_or_org": name})
            elif type(partsx) == list:
                # if we have a list of nameParts then the other mods/name fields & attributes must not
                # be present, but check this assumption
                if (
                    namex.get("role")
                    or namex.get("subNameWrapper")
                    or namex.get("type")
                ):
                    raise Exception(
                        "Unexpected mods/name structure with list of nameParts but also other fields: {name}"
                    )
                for partx in partsx:
                    for name in mklist(parse_name(partx)):
                        creators.append({"person_or_org": name})
        return creators

    @property
    def dates(self) -> list[dict[str, Any]]:
        dates = []
        # https://inveniordm.docs.cern.ch/reference/metadata/#dates-0-n
        # _additional_ (non-publication) dates structured like
        # { "date": "EDTF lvl 0 date", type: { "id": "TYPE" }, "description": "free text" }
        # types: accepted, available, collected, copyrighted, created, issued, other, submitted, updated, valid, withdrawn

        # dateCreatedWrapper/dateCaptured
        # ? should we add a "captured" date type? is "collected" close enough?
        dates_capturedx = mklist(
            self.xml.get("mods", {}).get("origininfo", {}).get("dateCaptured")
        )
        for dc in dates_capturedx:
            # work with strings and dicts
            dc = dc.get("#text") if type(dc) == dict else dc
            if dc:  # could be empty string
                dates.append(
                    {
                        "date": to_edtf(dc),
                        "type": {"id": "collected"},
                        "description": "date captured",
                    }
                )

        # we always have exactly one dateOtherWrapper and 0-1 dateOther, praise be
        date_other = (
            self.xml.get("mods", {})
            .get("origininfo", {})
            .get("dateOtherWrapper", {})
            .get("dateOther")
        )
        if type(date_other) == dict:
            date_other_text = to_edtf(date_other.get("#text"))
            if date_other_text:
                # the only types we have are Agreement and E/exhibit (case sensitive)
                date_type = date_other.get("@type", "")
                dates.append(
                    {
                        "date": date_other_text,
                        "type": {"id": "other"},
                        "description": date_type.capitalize(),
                    }
                )
        else:
            # dateOther with no attributes
            date_other_text = to_edtf(date_other)
            if date_other_text:
                dates.append({"date": date_other_text, "type": {"id": "other"}})
        return dates

    @property
    def descriptions(self) -> list[dict[str, Any]]:
        # extra /mods/abstract entries, mods/noteWrapper/note
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-descriptions-0-n
        # https://127.0.0.1:5000/api/vocabularies/descriptiontypes
        # types: abstract, methods, series-information, table-of-contents, technical-info, other

        desc = []
        if len(self.abstracts) > 1:
            desc.extend(
                [
                    {
                        "type": {"id": "abstract", "title": {"en": "Abstract"}},
                        "description": a,
                    }
                    for a in self.abstracts[1:]
                ]
            )

        # MODS note types: https://www.loc.gov/standards/mods/mods-notes.html
        # Mudflats has only handwritten & identification notes
        # All our note values: acquisition, action, additional artists, additional performers, additional physical form, depicted persons, exhibitions, funding, handwritten, identification, local, medium, original location, publications, source identifier, venue, version, version identification
        # TODO can we customize Invenio description types? https://127.0.0.1:5000/api/vocabularies/descriptiontypes
        noteWrappers = mklist(self.xml.get("mods", {}).get("noteWrapper", []))
        notes = []
        for wrapper in noteWrappers:
            notes = notes + mklist(wrapper.get("note", []))
        for note in notes:
            if type(note) == str and note:
                desc.append(
                    {
                        "type": {"id": "other", "title": {"en": "Other"}},
                        "description": note.strip(),
                    }
                )
            elif type(note) == dict:
                note = note.get("#text")
                if note:
                    desc.append(
                        {
                            "type": {"id": "other", "title": {"en": "Other"}},
                            "description": note.strip(),
                        }
                    )

        return desc

    @property
    def formats(self) -> list[str]:
        formats = set()
        for file in self.files:
            type = mimetypes.guess_type(file["filename"], strict=False)[0]
            if type:
                formats.add(type)
        return list(formats)

    @property
    def publication_date(self):
        # date created, add other/additional dates to self.dates[]
        # level 0 EDTF date (YYYY,  YYYY-MM, YYYY-MM-DD or slash separated range between 2 of these)
        # https://inveniordm.docs.cern.ch/reference/metadata/#publication-date-1
        # mods/originfo/dateCreatedWrapper/dateCreated (note lowercase origininfo) or item.createdDate
        origininfosx = mklist(self.xml.get("mods", {}).get("origininfo", {}))
        for origininfox in origininfosx:
            # use dateCreatedWrapper/dateCreated if we have it
            dateCreatedWrappersx = mklist(origininfox.get("dateCreatedWrapper"))
            for wrapper in dateCreatedWrappersx:
                dateCreatedsx = mklist(wrapper.get("dateCreated"))
                for dateCreated in dateCreatedsx:
                    # work around empty str or dict
                    if dateCreated:
                        # ! if a date isn't parseable then this returns None
                        if type(dateCreated) == str:
                            return to_edtf(dateCreated)
                        elif type(dateCreated) == dict:
                            return to_edtf(dateCreated.get("#text"))

                # maybe we have a range with pointStart and pointEnd elements?
                start = wrapper.get("pointStart")
                end = wrapper.get("pointEnd")
                if start and end:
                    # edtf.text_to_edtf(f"{start}/{end}") returns None for valid dates so we do this
                    return f"{to_edtf(start)}/{to_edtf(end)}"

            # maybe we have mods/origininfo/semesterCreated, which is always a string (no children)
            semesterCreated = origininfox.get("semesterCreated")
            if semesterCreated:
                return to_edtf(semesterCreated)

        # fall back on when the VAULT record was made (item.createdDate)
        return to_edtf(self.dateCreated)

    @property
    def publisher(self) -> str:
        # https://inveniordm.docs.cern.ch/reference/metadata/#publisher-0-1
        # ! In DataCite 4.5 the publisher field supports identifiers
        # https://datacite.org/blog/introducing-datacite-metadata-schema-4-5/#:~:text=text%20resourceType%20field.-,Identifiers%20for%20Publishers,-The%20DataCite%20Metadata
        # Invenio will probably need to change it to a { id, name } dict & we
        # can use CCA's ROR ID but no idea how long that will take to happen

        # 1) DBR articles have a variable publisher depending on date:
        #     Winter 1983 - Spring 1990: Design Book Review
        #     Winter 1991 - Winter/Spring 1995: MIT Press
        #     Winter 1996/1997: Design Book Review
        #     1997 - on: California College of the Arts
        # https://vault.cca.edu/items/bd3b483b-52b9-423c-a96e-d37863511d75/1/%3CXML%3E
        # mods/relatedItem[@type="host"]/titleInfo/title == DBR
        related_item = self.xml.get("mods", {}).get("relatedItem", {})
        related_title_infos = mklist(related_item.get("titleInfo"))
        for ti in related_title_infos:
            if ti.get("title") == "Design Book Review":
                issue = related_item.get("part", {}).get("detail", {}).get("number")
                if issue:
                    # there are some double issues with numbers like 37/38
                    issue = int(issue[:2])
                    if issue < 19:
                        return "Design Book Review"
                    elif issue < 36:
                        return "MIT Press"
                    elif issue < 39:
                        return "Design Book Review"
                    else:
                        return "California College of the Arts"

        # 2) CCA/C archives has publisher info mods/originInfo/publisher
        # https://vault.cca.edu/items/c4583fe6-2e85-4613-a1bc-774824b3e826/1/%3CXML%3E
        # records have multiple originInfo nodes
        originInfos = mklist(self.xml.get("mods", {}).get("originInfo"))
        for originInfo in originInfos:
            publisher = originInfo.get("publisher")
            if type(publisher) == dict:
                publisher = publisher.get("#text")
            if publisher:
                return publisher.strip()

        # 3) Press Clips items are not CCA but have only publication, not publisher, info
        # 4) Student work has no publisher
        return ""

    @property
    def related_identifiers(self) -> list[dict[str, str | dict[str, str]]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#related-identifiersworks-0-n
        # # relation types: cites, compiles, continues, describes, documents, haspart, hasversion, iscitedby, iscompiledby, iscontinuedby, isderivedfrom, isdescribedby, isdocumentedby, isidenticalto, isnewversionof, isobsoletedby, isoriginalformof, ispartof, ispreviousversionof, isreferencedby, isrequiredby, isreviewedby, issourceof, issupplementto, issupplementedby
        # related_identifiers don't seem to be indexed in the search engine, searches like
        # _exists_:metadata.related_identifiers returns items but metadata.related_identifiers:($URL) does not
        ri = []
        if self.vault_url:
            # add a URL identifier for the old VAULT item
            ri.append(
                {
                    "identifier": self.vault_url,
                    "relation_type": {
                        "id": "isnewversionof",
                        "title": {"en": "Is new version of"},
                    },
                    "scheme": "url",
                }
            )
        # TODO there are probably other relations we can add, like mods/relatedItem|relateditem
        # but if a VAULT item is related to another VAULT item, we need to know both their new
        # IDs in Invenio to create the relation
        return ri

    @property
    def resource_type(self) -> dict[str, str]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#resource-type-1
        # https://127.0.0.1:5000/api/vocabularies/resourcetypes
        # There are many fields that could be used to determine the resource type. Priority:
        # 1. mods/typeOfResource, 2. local/courseWorkType, 3. TBD (there are more...)
        # mods/typeOfResourceWrapper/typeOfResource
        # Take the first typeOfResource value we find
        wrapper = self.xml.get("mods", {}).get("typeOfResourceWrapper")
        if type(wrapper) == list:
            wrapper = wrapper[0]
        if type(wrapper) == dict:
            rtype = wrapper.get("typeOfResource", "")
            if type(rtype) == list:
                rtype = rtype[0]
            if type(rtype) == dict:
                rtype = rtype.get("#text", "")
            if rtype in resource_type_map:
                return {"id": resource_type_map[rtype]}

        # TODO local/courseWorkType

        # default to publication
        return {"id": "publication"}

    @property
    def rights(self) -> List[dict[str, str | dict[str, str]]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#rights-licenses-0-n
        # https://127.0.0.1:5000/api/vocabularies/licenses
        # ! returned id values MUST be IDs from licenses.csv in cca/cca_invenio
        # We always have exactly one accessCondition node, str or dict
        accessCondition = self.xml.get("mods", {}).get("accessCondition", "")
        if type(accessCondition) == dict:
            # if we have a href attribute prefer that
            href = accessCondition.get("@href", None)
            if href and href in license_href_map:
                return [{"id": license_href_map[href]}]
            # if we didn't find a usable href then use the text
            accessCondition = accessCondition.get("#text", "")

        # use substring matching—some long ACs contain the license name or URL
        for key in license_text_map.keys():
            if key in accessCondition:
                return [{"id": license_text_map[key]}]

        # default to copyright
        return [{"id": "copyright"}]

    @property
    def sizes(self) -> list[str]:
        # mods/physicalDescription/extent
        # https://inveniordm.docs.cern.ch/reference/metadata/#sizes-0-n
        extents = []

        extent = self.xml.get("mods", {}).get("physicalDescription", {}).get("extent")
        if type(extent) == dict:
            extent = extent.get("#text")
        if extent:
            extents.append(extent)

        # TODO there will be /local extent values in student work items
        return extents

    @property
    def subjects(self) -> list[dict[str, str]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#subjects-0-n
        # Subjects are {id} or {subject} dicts
        # TODO handling name subjects (right now they're added as keywords)
        # find_subjects pulls from mods/subject and mods/genreWrapper/genre
        subjects: set[Subject] = find_subjects(self.xml)
        return [s.to_invenio() for s in subjects]

    def get(self) -> dict[str, Any]:
        return {
            # TODO restricted access based on local/viewLevel value
            "access": {
                "files": "public",
                "record": "public",
            },
            # ! blocked until we know what custom fields we'll have
            "custom_fields": {},
            # TODO add files, figure out best one to show first (prefer image formats?)
            "files": {
                "enabled": bool(len(self.files)),
                "order": [],
            },
            # "files": {
            #     "enabled": bool(len(self.files)),
            #     "order": self.files,
            # },
            "metadata": {
                "additional_descriptions": self.descriptions,
                "additional_titles": self.addl_titles,
                # mods/name/namePart, non-creator contributors
                # https://inveniordm.docs.cern.ch/reference/metadata/#contributors-0-n
                # "persons or organisations that have contributed, but which should not be credited for citation purposes"
                # ? is this ever relevant for us?
                "contributors": [],
                "creators": self.creators,
                "dates": self.dates,
                "description": self.abstracts[0],
                "formats": self.formats,
                # https://inveniordm.docs.cern.ch/reference/metadata/#locations-0-n
                # not available on deposit form and does not display anywhere, skip for now
                "locations": {"features": []},
                "publication_date": self.publication_date,
                "publisher": self.publisher,
                "related_identifiers": self.related_identifiers,
                "resource_type": self.resource_type,
                "rights": self.rights,
                # not on deposit form but displays in right-side Details under resource type and formats
                "sizes": self.sizes,
                "subjects": self.subjects,
                "title": self.title,
            },
            # https://inveniordm.docs.cern.ch/reference/metadata/#parent
            # API ignores this, cannot define owner nor community in initial request
            # "parent": {},
        }


if __name__ == "__main__":
    # we assume first arg is path to the item JSON
    for file in sys.argv[1:]:
        items = find_items(file)
        for item in items:
            r = Record(item)
            # JSON pretty print record
            json.dump(r.get(), sys.stdout, indent=2)
