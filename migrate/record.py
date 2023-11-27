"""
Convert an EQUELLA item into an Invenio record.

Eventually this will accept a _directory_ containing the item's JSON and its
attachments, but for staters we are taking just JSON.
"""
from datetime import date
import json
import re
import sys
from typing import Any

import xmltodict

from names import parse_name
from maps import resource_type_map, role_map
from utils import find_items, mklist, to_edtf


def postprocessor(path, key, value):
    """XML postprocessor, ensure that empty XML nodes like <foo></foo> are empty
    dicts, not None, so we can continue chaining .get() calls on the result."""
    if value is None:
        return (key, {})
    return (key, value)


class Record:
    def __init__(self, item):
        self.xml = xmltodict.parse(item["metadata"], postprocessor=postprocessor)["xml"]
        self.title = item.get("name", "Untitled")
        # default to current date in ISO 8601 format
        self.dateCreated = item.get("dateCreated", date.today().isoformat())

    @property
    def abstracts(self) -> list:
        abs = self.xml.get("mods", {}).get("abstract", "")
        return mklist(abs)

    @property
    def descriptions(self) -> list[dict[str, Any]]:
        # extra /mods/abstract entries, mods/noteWrapper/note
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-descriptions-0-n
        # https://127.0.0.1:5000/api/vocabularies/descriptiontypes
        # types: abstract, methods, series-information, table-of-contents, technical-info, other

        # we ensure there's at least one abstract (see def abstracts)
        desc = [{"type": "abstract", "description": a} for a in self.abstracts[1:]]

        # MODS note types: https://www.loc.gov/standards/mods/mods-notes.html
        # Mudflats has only handwritten & identification notes
        # All our note values: acquisition, action, additional artists, additional performers, additional physical form, depicted persons, exhibitions, funding, handwritten, identification, local, medium, original location, publications, source identifier, venue, version, version identification
        notes = mklist(self.xml.get("mods", {}).get("noteWrapper", {}).get("note"))
        for note in notes:
            if type(note) == str:
                desc.append({"type": "other", "description": note})
            elif type(note) == dict:
                desc.append({"type": "other", "description": note.get("#text")})

        return desc

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
                # TODO once we have CCA ROR in our vocab, use an identifier & not name string
                affs = set()
                subnamesx = mklist(namex.get("subNameWrapper"))
                for subnamex in subnamesx:
                    if subnamex.get("ccaAffiliated") == "Yes":
                        affs.add("California College of the Arts")
                        # skip our false positives of ccaAffiliated: No | affiliation: CCA
                    elif subnamex.get("affiliation"):
                        affsx = mklist(subnamex.get("affiliation"))
                        for affx in affsx:
                            if not re.match(r"CCA/?C?", affx, flags=re.IGNORECASE):
                                affs.add(subnamex.get("affiliation"))
                # convert the affiliations set to {"name": affiliation} dicts"
                creator["affiliations"] = [{"name": aff} for aff in affs]

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
                        # ! if a date isn't parseable then this will return None
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

        # TODO origininfo/dateOtherWrapper
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
    def type(self) -> dict[str, str]:
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
                "enabled": False,
                "order": [],
            },
            "metadata": {
                "additional_descriptions": self.descriptions,
                "additional_titles": self.addl_titles,
                # mods/name/namePart, non-creator contributors
                "contributors": [],
                "creators": self.creators,
                "dates": self.dates,
                "description": self.abstracts[0],
                "formats": [],
                "locations": [],
                "publication_date": self.publication_date,
                "publisher": "",
                # relation types: cites, compiles, continues, describes, documents, haspart, hasversion, iscitedby, iscompiledby, iscontinuedby, isderivedfrom, isdescribedby, isdocumentedby, isidenticalto, isnewversionof, isobsoletedby, isoriginalformof, ispartof, ispreviousversionof, isreferencedby, isrequiredby, isreviewedby, issourceof, issupplementto, issupplementedby
                "related_identifiers": [],
                # options defined in resource_types.yaml fixture
                # https://inveniordm.docs.cern.ch/reference/metadata/#resource-type-1
                "resource_type": self.type,
                # mods/accessCondition with license URL in href attribute
                # https://127.0.0.1:5000/api/vocabularies/licenses
                # https://inveniordm.docs.cern.ch/reference/metadata/#rights-licenses-0-n
                # options defined in licenses.csv fixture
                "rights": [],
                "sizes": [],
                "subjects": [],
                "title": self.title,
            },
            # https://inveniordm.docs.cern.ch/reference/metadata/#parent
            # ? Does adding a parent community while creating the draft work or do
            # ? we have to use additional API calls afterwards?
            # ? Can we specifiy parent.access.owned_by here to set the owner?
            # collection, mods/relatedItem?
            "parent": {"communities": {}},
        }


if __name__ == "__main__":
    # we assume first arg is path to the item JSON
    for file in sys.argv[1:]:
        items = find_items(file)
        for item in items:
            r = Record(item)
            # JSON pretty print record
            json.dump(r.get(), sys.stdout, indent=2)
