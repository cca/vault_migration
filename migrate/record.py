"""
Convert an EQUELLA item into an Invenio record.

Eventually this will accept a _directory_ containing the item's JSON and its
attachments, but for staters we are taking just JSON.
"""

import json
import mimetypes
import re
import sys
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any

import xmltodict
from maps import (
    communities_map,
    license_href_map,
    license_text_map,
    resource_type_map,
    role_map,
)
from names import parse_name
from subjects import Subject, find_subjects
from utils import (
    cca_affiliation,
    find_items,
    get_url,
    mklist,
    syllabus_collection_uuid,
    to_edtf,
    visual_mime_type_sort,
)

# load archives series JSON if we have it
archives_series_vocab: dict[str, list[str]] = {}
archives_series_path = Path(__file__).parent / "archives_series.json"
if archives_series_path.exists():
    with open(archives_series_path, "r") as fh:
        archives_series_vocab = json.load(fh)


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
        self.attachments: list[dict[str, Any]] = sorted(
            [
                a
                for a in item.get("attachments", [])
                if a["type"] in ("file", "htmlpage", "zip")
            ],
            key=visual_mime_type_sort,
        )
        # normalize EQUELLA attachment names, see logic in equella_scripts/collection-export:
        # https://github.com/cca/equella_scripts/blob/3dd8ca3e35e7b316beb6b399cab0d09281a12bda/collection-export/collect.js#L109-L129
        # TODO what about filenames changed by filenamify like unpacked zips?
        for a in self.attachments:
            a["name"] = a.get("filename") or re.sub(r"_zips\/", "", a["folder"])
            if a["type"] == "htmlpage":
                a["name"] = f"{a['uuid']}.html"
        # default to current date in ISO 8601 format
        self.createdDate: str = item.get("createdDate", date.today().isoformat())
        # url and "custom" youtube attachments
        self.references: list[dict[str, Any]] = [
            a for a in item.get("attachments", []) if a["type"] in ("url", "youtube")
        ]
        self.title: str = item.get("name", "Untitled")
        self.vault_collection: str = item.get("collection", {}).get("uuid", "")
        self.vault_url: str = ""
        if item.get("uuid") and item.get("version"):
            self.vault_url = (
                f"https://vault.cca.edu/items/{item['uuid']}/{item['version']}/"
            )
        self.xml = xmltodict.parse(item["metadata"], postprocessor=postprocessor)["xml"]

    @cached_property
    def abstracts(self) -> list:
        abs = mklist(self.xml.get("mods", {}).get("abstract", ""))
        # filter out all empty strings except the first one
        for idx, a in enumerate(abs):
            if idx > 0 and not a:
                abs.remove(a)
        return abs

    @cached_property
    def addl_titles(self) -> list[dict[str, str]]:
        # extra /mods/titleInfo/title entries, titleInfo/subtitle
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-titles-0-n
        # types: alternative-title, descriptive-title, other, subtitle, transcribed-title, translated-title
        # https://github.com/cca/cca_invenio/blob/main/app_data/vocabularies/title_types.yaml
        atitles = []
        titleinfos = mklist(self.xml.get("mods", {}).get("titleInfo"))
        for idx, titleinfo in enumerate(titleinfos):
            # all subtitles
            for subtitle in mklist(titleinfo.get("subTitle")):
                atitles.append({"title": subtitle, "type": {"id": "subtitle"}})
            # titles other than the first
            for title in mklist(titleinfo.get("title")):
                if idx > 0:
                    ttype = titleinfo.get("@type")
                    if ttype == "alternative":
                        atitles.append(
                            {"title": title, "type": {"id": "alternative-title"}}
                        )
                    elif ttype == "descriptive":
                        atitles.append(
                            {"title": title, "type": {"id": "descriptive-title"}}
                        )
                    elif ttype == "transcribed":
                        atitles.append(
                            {"title": title, "type": {"id": "transcribed-title"}}
                        )
                    elif ttype == "translated":
                        atitles.append(
                            {"title": title, "type": {"id": "translated-title"}}
                        )
                    else:
                        atitles.append({"title": title, "type": {"id": "other"}})
        return atitles

    @cached_property
    def archives_series(self) -> dict[str, str] | None:
        archives_wrapper = self.xml.get("local", {}).get("archivesWrapper")
        series = archives_wrapper.get("series") if archives_wrapper else None
        if series and series not in archives_series_vocab:
            # Inconsistency but it doesn't rise to the point of an Exception
            print(f'Warning: series "{series}" is not in CCA/C Archives Series')
        subseries = archives_wrapper.get("subseries", "") if archives_wrapper else None
        if (
            subseries
            and series
            and subseries not in archives_series_vocab.get(series, [])
        ):
            print(f'Warning: subseries "{subseries}" not found under series "{series}"')
        if series and not subseries:
            raise Exception(f"Archives Series without Subseries: {self.vault_url}")
        if series and subseries:
            return {"series": series, "subseries": subseries}
        return {}

    @cached_property
    def course(self) -> dict[str, Any] | None:
        course_info = self.xml.get("local", {}).get("courseInfo")
        if course_info and type(course_info) is dict:
            # we can construct section_calc_id if we know both section & term
            section: str = course_info.get("section", "")
            term: str = course_info.get("semester", "")
            if section and term:
                section_calc_id: str = f"{section}_AP_{term.replace(' ', '_')}"
            else:
                section_calc_id = ""
            return {
                "department": self.xml.get("local", {}).get("department", ""),
                "department_code": course_info.get("department", ""),
                # we may have instructor usernames in courseInfo/facultyID
                # but none of the other elements needed to construct an
                # instructor object so we skip it
                "instructors_string": course_info.get("faculty", ""),
                "section": section,
                "section_calc_id": section_calc_id,
                "term": term,
                "title": course_info.get("course", ""),
            }
        return None

    @cached_property
    def communities(self) -> set[str]:
        """List of community shortnames for the record to be included in. A record can be in multiple
        communities, but there is no need to add it to a parent community if it is in a child (e.g.
        Libraries AND Mudflats, if we choose hierarchical communities).

        Communities exists outside record metadata and aren't in Record.get(). It is up to a migrate
        script to use this set to add a record to its communities (e.g., by using the REST API)."""
        communities: set[str] = set()

        if self.vault_collection in communities_map:
            communities.add(communities_map[self.vault_collection])

        related_items: list[dict[str, Any]] = mklist(
            self.xml.get("mods", {}).get("relatedItem", {})
        )
        for ri in related_items:
            if ri.get("@type") == "host":
                title: str | None = ri.get("title")
                if title and title in communities_map:
                    communities.add(communities_map[title])
                    # we don't need to add the parent Libraries community if we have a child
                    communities.discard("libraries")

        return communities

    @cached_property
    def creators(self) -> list[dict[str, Any]]:
        # mods/name
        # https://inveniordm.docs.cern.ch/reference/metadata/#creators-1-n
        creators: list[dict[str, Any]] = []
        for namex in mklist(self.xml.get("mods", {}).get("name")):
            # @usage = primary, secondary | ignoring this but could say sec. -> contributor, not creator
            partsx = namex.get("namePart")
            if type(partsx) is str:
                # initialize, use affiliation set to dedupe them
                creator = {"person_or_org": {}, "affiliations": [], "role": {}}

                # Role: creators can only have one role, take the first one
                rolex = mklist(namex.get("role", {}).get("roleTerm"))
                if len(rolex):
                    rolex = rolex[0]
                    role: str = rolex if type(rolex) is str else rolex.get("#text")
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
                if type(names) is dict:
                    creators.append(
                        {
                            "affiliations": creator["affiliations"],
                            "person_or_org": names,
                            "role": creator["role"],
                        }
                    )
                # implies type(names) == list, similar to below, if parse_name returns a
                # list of names but we have role/affiliation then something is wrong
                elif creator.get("role") or len(creator.get("affiliation", [])):
                    raise Exception(
                        f"Unexpected mods/name structure: parse_name(namePart) returned a list but we also have role/affiliation. Name: {namex}"
                    )
                elif type(names) is list:
                    for name in names:
                        creators.append({"person_or_org": name})
            elif type(partsx) is list:
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

        # Syllabi: we have no mods/name but list faculty in courseInfo/faculty
        if len(creators) == 0:
            faculty = self.xml.get("local", {}).get("courseInfo", {}).get("faculty")
            if faculty:
                names = parse_name(faculty)
                if type(names) is dict:
                    creators.append(
                        {
                            "affiliations": cca_affiliation,
                            "person_or_org": names,
                            "role": {"id": "creator"},
                        }
                    )
                elif type(names) is list:
                    for name in names:
                        creators.append(
                            {
                                "affiliations": cca_affiliation,
                                "person_or_org": name,
                                "role": {"id": "creator"},
                            }
                        )

        # If we _still_ have no creators, we cannot create a record b/c it is a
        # required field but for our test data I do not want to specify creators.
        if len(creators) == 0 and "pytest" not in sys.modules:
            raise Exception(f"Record has no creators: {self.title}\n{self.vault_url}")
        return creators

    @cached_property
    def custom_fields(self) -> dict[str, Any]:
        cf: dict[str, Any] = {}
        # 1) ArchivesSeries custom field, { series, subseries } dict
        if self.archives_series:
            cf["cca:archives_series"] = self.archives_series
        if self.course:
            cf["cca:course"] = self.course
        return cf

    @cached_property
    def dates(self) -> list[dict[str, Any]]:
        dates = []
        # https://inveniordm.docs.cern.ch/reference/metadata/#dates-0-n
        # _additional_ (non-publication) dates structured like
        # { "date": "EDTF lvl 0 date", type: { "id": "TYPE" }, "description": "free text" }
        # types: available, collected, copyrighted, created, other, submitted, updated, withdrawn
        # https://github.com/cca/cca_invenio/blob/main/app_data/vocabularies/date_types.yaml

        # dateCreatedWrapper/dateCaptured
        dates_capturedx = mklist(
            self.xml.get("mods", {}).get("origininfo", {}).get("dateCaptured")
        )
        for dc in dates_capturedx:
            # work with strings and dicts
            dc = dc.get("#text") if type(dc) is dict else dc
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
        if type(date_other) is dict:
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

    @cached_property
    def descriptions(self) -> list[dict[str, Any]]:
        # extra /mods/abstract entries, mods/noteWrapper/note
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-descriptions-0-n
        # /api/vocabularies/descriptiontypes
        # types: abstract, methods, series-information, table-of-contents, technical-info, other
        # https://datacite-metadata-schema.readthedocs.io/en/4.5/properties/description/#a-descriptiontype
        # ? do we want to define our own description types?
        # One option: https://art-and-rare-materials-bf-ext.github.io/arm/v1.0/vocabularies/note_types.html

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

        # we have _many_ MODS note types & none map cleanly to Invenio description types
        noteWrappers = mklist(self.xml.get("mods", {}).get("noteWrapper", []))
        notes = []
        for wrapper in noteWrappers:
            notes = notes + mklist(wrapper.get("note", []))
        for note in notes:
            if type(note) is str and note:
                desc.append(
                    {
                        "type": {"id": "other", "title": {"en": "Other"}},
                        "description": note.strip(),
                    }
                )
            elif type(note) is dict:
                # prefix note with its type if we have one
                ntype: str = note.get("@type", "").title()
                note_text: str = note.get("#text", "")
                note_text = (
                    f"{ntype}: {note_text}" if ntype and note_text else note_text
                )
                if note_text:
                    desc.append(
                        {
                            "type": {"id": "other", "title": {"en": "Other"}},
                            "description": note_text.strip(),
                        }
                    )

        return desc

    @cached_property
    def formats(self) -> list[str]:
        formats = set()
        for file in self.attachments:
            type = mimetypes.guess_type(file["name"], strict=False)[0]
            if type:
                formats.add(type)
        return list(formats)

    @cached_property
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
                        edtf_date: str | None = None
                        if type(dateCreated) is str:
                            edtf_date = to_edtf(dateCreated)
                        elif type(dateCreated) is dict:
                            edtf_date = to_edtf(dateCreated.get("#text"))

                        if edtf_date:
                            return edtf_date

                # maybe we have a range with pointStart and pointEnd elements?
                # edtf.text_to_edtf(f"{start}/{end}") returns None for valid dates so do in two steps
                start: str | None = to_edtf(wrapper.get("pointStart"))
                end: str | None = to_edtf(wrapper.get("pointEnd"))
                if start and end:
                    return f"{start}/{end}"

            # maybe we have mods/origininfo/semesterCreated, which is always a string (no children)
            semesterCreated = origininfox.get("semesterCreated")
            if semesterCreated:
                edtf_date: str | None = to_edtf(semesterCreated)
                if edtf_date:
                    return edtf_date

        # fall back on when the VAULT record was made (item.createdDate)
        return to_edtf(self.createdDate)

    @cached_property
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
            if type(publisher) is dict:
                publisher = publisher.get("#text")
            if publisher:
                return publisher.strip()

        # 3) Press Clips items are not CCA but have only publication, not publisher, info
        # 4) Student work has no publisher
        return ""

    @cached_property
    def related_identifiers(self) -> list[dict[str, str | dict[str, str]]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#related-identifiersworks-0-n
        # Default relation types: https://github.com/inveniosoftware/invenio-rdm-records/blob/master/invenio_rdm_records/fixtures/data/vocabularies/relation_types.yaml
        # We use a reduced subset since there are too many
        # related_identifiers aren't indexed in the search engine, searches like
        # _exists_:metadata.related_identifiers returns items but metadata.related_identifiers:($URL) does not
        ri = []
        if self.vault_url:
            # add a URL identifier for the old VAULT item
            ri.append(
                {
                    "identifier": self.vault_url,
                    "relation_type": {"id": "isnewversionof"},
                    "scheme": "url",
                }
            )
        # URL or YouTube attachments, examples:
        # 1) url https://vault.cca.edu/items/6bf89d87-abea-4367-b008-9304122364b0/1/
        # 2) url https://vault.cca.edu/items/951e8540-4c0e-4a5a-a8c0-4b95a7045edd/1
        # 3) youtube https://vault.cca.edu/items/1948b890-cee5-45d3-9d0b-266543b83155/1/
        for link in filter(lambda a: a["type"] in ("url", "youtube"), self.references):
            url: str | None = get_url(link.get("url") or link["viewUrl"])
            if url:
                ri.append(
                    {
                        "identifier": url,
                        "relation_type": {"id": "haspart"},
                        "scheme": "url",
                    }
                )
        # TODO there are other relations to add, like mods/relatedItem|relateditem
        # Example: https://vault.cca.edu/items/2a1bbc39-0619-4f95-8573-dcf4fd9c9e61/2/
        # but if a VAULT item is related to another VAULT item, we need to know both their new
        # IDs in Invenio to create the relation
        return ri

    @cached_property
    def resource_type(self) -> dict[str, str]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#resource-type-1
        # https://github.com/cca/cca_invenio/blob/main/app_data/vocabularies/resource_types.yaml
        # There are many fields that could be used to determine the resource type. Priority:
        # 1. mods/typeOfResource, 2. local/courseWorkType, 3. TBD (there are more...)
        # mods/typeOfResourceWrapper/typeOfResource

        # Syllabus Collection only contains syllabi
        if self.vault_collection == syllabus_collection_uuid:
            return {"id": "publication-syllabus"}

        # Take the first typeOfResource value we find
        wrapper = self.xml.get("mods", {}).get("typeOfResourceWrapper")
        if type(wrapper) is list:
            wrapper = wrapper[0]
        if type(wrapper) is dict:
            rtype = wrapper.get("typeOfResource", "")
            if type(rtype) is list:
                rtype = rtype[0]
            if type(rtype) is dict:
                rtype = rtype.get("#text", "")
            if rtype in resource_type_map:
                return {"id": resource_type_map[rtype]}

        # TODO local/courseWorkType

        # default to publication
        return {"id": "publication"}

    @cached_property
    def rights(self) -> list[dict[str, str | dict[str, str]]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#rights-licenses-0-n
        # Choices: https://github.com/cca/cca_invenio/blob/main/app_data/vocabularies/licenses.csv
        # We always have exactly one accessCondition node, str or dict
        accessCondition = self.xml.get("mods", {}).get("accessCondition", "")
        if type(accessCondition) is dict:
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

    @cached_property
    def sizes(self) -> list[str]:
        # mods/physicalDescription/extent
        # https://inveniordm.docs.cern.ch/reference/metadata/#sizes-0-n
        extents = []

        extent = self.xml.get("mods", {}).get("physicalDescription", {}).get("extent")
        if type(extent) is dict:
            extent = extent.get("#text")
        if extent:
            extents.append(extent)

        # TODO there will be /local extent values in student work items
        return extents

    @cached_property
    def subjects(self) -> list[dict[str, str]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#subjects-0-n
        # Subjects are {id} or {subject} dicts
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
            "custom_fields": self.custom_fields,
            "files": {
                "enabled": bool(len(self.attachments)),
                # ! API drops these, whether we define before adding files or after
                "order": [att["name"] for att in self.attachments],
                "default_preview": (
                    self.attachments[0]["name"] if len(self.attachments) else ""
                ),
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
