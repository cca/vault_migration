"""
Convert an EQUELLA item into an Invenio record.

To test record conversion, we can pass this script a path to one or more XML
files, single JSON items, or JSON search results and it will print Invenio
record JSON to stdout.
"""

import json
import mimetypes
import re
import sys
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from maps import (
    communities_map,
    form_broad_map,
    license_href_map,
    license_text_map,
    resource_type_map,
    role_map,
)
from names import parse_name
from subjects import Subject, find_subjects
from utils import (
    art_collection_uuid,
    cca_affiliation,
    find_items,
    get_url,
    libraries_eresources_uuid,
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
        # expose EQUELLA item XML as an element tree
        self.etree = ElementTree.XML(item["metadata"])
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

    @cached_property
    def abstracts(self) -> list[str]:
        abstract_elements: list[Element] = self.etree.findall("./mods/abstract")
        abstracts: list[str] = []
        for abstract in abstract_elements:
            if abstract.text:
                abstracts.append(abstract.text)
        return abstracts

    @cached_property
    def access(self) -> dict[str, Literal["public", "restricted"]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#access
        # ! does defaulting to restricted make sense? should we use different
        # ! defaults for different collections?
        access: dict[str, Literal["public", "restricted"]] = {
            "files": "restricted",
            "record": "restricted",
        }
        view_level: str | None = self.etree.findtext("./local/viewLevel")
        if view_level and view_level.strip().lower() == "public":
            access["files"] = "public"
            access["record"] = "public"
        return access

    @cached_property
    def addl_titles(self) -> list[dict[str, str]]:
        # extra /mods/titleInfo/title entries, titleInfo/subtitle
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-titles-0-n
        # types: alternative-title, descriptive-title, other, subtitle, transcribed-title, translated-title
        # https://github.com/cca/cca_invenio/blob/main/app_data/vocabularies/title_types.yaml
        atitles: list[dict[str, Any]] = []
        for idx, titleinfo in enumerate(self.etree.findall("./mods/titleInfo")):
            # all subtitles
            for subtitle in titleinfo.findall("subTitle"):
                if subtitle.text:
                    atitles.append({"title": subtitle.text, "type": {"id": "subtitle"}})
            # titles other than the first
            for title in titleinfo.findall("title"):
                if idx > 0 and title.text:
                    ttype: str | None = titleinfo.get("type")
                    if ttype == "alternative":
                        atitles.append(
                            {"title": title.text, "type": {"id": "alternative-title"}}
                        )
                    elif ttype == "descriptive":
                        atitles.append(
                            {"title": title.text, "type": {"id": "descriptive-title"}}
                        )
                    elif ttype == "transcribed":
                        atitles.append(
                            {"title": title.text, "type": {"id": "transcribed-title"}}
                        )
                    elif ttype == "translated":
                        atitles.append(
                            {"title": title.text, "type": {"id": "translated-title"}}
                        )
                    else:
                        atitles.append({"title": title.text, "type": {"id": "other"}})
        return atitles

    @cached_property
    def archives_series(self) -> dict[str, str] | None:
        series: str | None = self.etree.findtext("./local/archivesWrapper/series")
        if series and series not in archives_series_vocab:
            # Inconsistency but it doesn't rise to the point of an Exception
            print(
                f'Warning: series "{series}" is not in CCA/C Archives Series',
                file=sys.stderr,
            )
        subseries: str | None = self.etree.findtext("./local/archivesWrapper/subseries")
        if (
            subseries
            and series
            and subseries not in archives_series_vocab.get(series, [])
        ):
            print(
                f'Warning: subseries "{subseries}" not found under series "{series}"',
                file=sys.stderr,
            )
        if series and not subseries:
            raise Exception(f"Archives Series without Subseries: {self.vault_url}")
        if series and subseries:
            return {"series": series, "subseries": subseries}
        return {}

    @cached_property
    def course(self) -> dict[str, Any] | None:
        course_info: Element | None = self.etree.find("./local/courseInfo")
        if course_info and any(s for s in course_info.itertext() if s):
            # we can construct section_calc_id if we know both section & term
            section: str = course_info.findtext("./section") or ""
            term: str = course_info.findtext("./semester") or ""
            if section and term:
                section_calc_id: str = f"{section}_AP_{term.replace(' ', '_')}"
            else:
                section_calc_id = ""
            return {
                "department": self.etree.findtext("./local/department") or "",
                "department_code": course_info.findtext("department") or "",
                # we may have instructor usernames in courseInfo/facultyID
                # but none of the other elements needed to construct an
                # instructor object so we skip it
                "instructors_string": course_info.findtext("faculty") or "",
                "section": section,
                "section_calc_id": section_calc_id,
                "term": term,
                "title": course_info.findtext("course") or "",
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

        if self._is_artists_book:
            communities.add("artists-books")
            communities.discard("libraries")  # libraries is implied

        for ri in self.etree.findall("./mods/relatedItem"):
            if ri.get("type") == "host":
                title: str | None = ri.findtext("title")
                if title and title in communities_map:
                    communities.add(communities_map[title])
                    communities.discard("libraries")  # libraries is implied

        return communities

    @cached_property
    def creators(self) -> list[dict[str, Any]]:
        # mods/name for most items, local/courseInfo/faculty for Syllabi, and
        # titleInfo/title split author from "Title / Author" for Artists Books
        # https://inveniordm.docs.cern.ch/reference/metadata/#creators-1-n
        creators: list[dict[str, Any]] = []
        for name_element in self.etree.findall("./mods/name"):
            # @usage = primary, secondary | ignoring this but could say sec. -> contributor, not creator
            name_parts: list[Element] = name_element.findall("namePart")
            if len(name_parts) == 1:
                name_part_text: str | None = name_parts[0].text
                if name_part_text:
                    # initialize, use affiliation set to dedupe them
                    creator: dict[str, Any] = {
                        "person_or_org": {},
                        "affiliations": [],
                        "role": {},
                    }

                    # Role: creators can only have one role, take the first one
                    role_text: str | None = name_element.findtext("./role/roleTerm")
                    if role_text:
                        role_text = role_text.lower().replace(" ", "")
                        if role_text in role_map:
                            creator["role"]["id"] = role_map[role_text]
                        else:
                            # means role doesn't need to be mapped
                            creator["role"]["id"] = role_text

                    affiliations: list[dict[str, str]] = []
                    for subname_wrapper in name_element.findall("./subNameWrapper"):
                        if subname_wrapper.findtext("./ccaAffiliated") == "Yes":
                            affiliations.append({"id": "01mmcf932"})
                        elif subname_wrapper.findtext("./affiliation"):
                            # skip our false positives of ccaAffiliated: No | affiliation: CCA
                            for aff_element in subname_wrapper.findall("./affiliation"):
                                if (
                                    aff_element.text
                                    and not re.match(
                                        r"CCA/?C?",
                                        aff_element.text,
                                        flags=re.IGNORECASE,
                                    )
                                    and not re.match(
                                        r"California College of (the)? Arts (and Crafts)?",
                                        aff_element.text,
                                        flags=re.IGNORECASE,
                                    )
                                ):
                                    affiliations.append({"name": aff_element.text})
                    # dedupe the list of affiliation dicts
                    creator["affiliations"] = list(
                        {frozenset(d.items()): d for d in affiliations}.values()
                    )

                    names = parse_name(name_part_text)
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
                            f"Unexpected mods/name structure: parse_name(namePart) returned a list but we also have role/affiliation. Name: {name_element}"
                        )
                    elif type(names) is list:
                        for name in names:
                            creators.append({"person_or_org": name})
            elif len(name_parts) > 1:
                # if we have a list of nameParts then the other mods/name fields & attributes must not
                # be present, but check this assumption
                if (
                    name_element.findtext("role")
                    or name_element.findtext("subNameWrapper")
                    or name_element.findtext("type")
                ):
                    raise Exception(
                        f"""Unexpected mods/name structure with list of nameParts but also other fields.
Attributes: {name_element.attrib}
Children: {[(c.tag, c.text) for c in name_element]}"""
                    )
                for name_part in name_parts:
                    if name_part.text:
                        # TODO fix parse_name to always return a list then delete mklist
                        for name in mklist(parse_name(name_part.text)):
                            creators.append({"person_or_org": name})

        # Syllabi: we have no mods/name but list faculty in courseInfo/faculty
        if len(creators) == 0:
            faculty: str | None = self.etree.findtext("./local/courseInfo/faculty")
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
                        creators.append({"person_or_org": name})

        # artists books have creator in title like "title / author"
        if self._is_artists_book:
            title: str | None = self.etree.findtext("./mods/titleInfo/title")
            assert isinstance(title, str), (
                f"Artists Book missing title: {self.vault_url}"
            )
            title_parts: list[str] = title.split(" / ")
            assert len(title_parts) == 2, (
                f"Title is missing author part: {title} | {self.vault_url}"
            )
            self.title = title_parts[0].strip()
            author: str = title_parts[1].strip()
            if author:
                names = parse_name(author)
                if type(names) is dict:
                    creators.append({"person_or_org": names})
                elif type(names) is list:
                    for name in names:
                        creators.append({"person_or_org": name})

        # If we _still_ have no creators, we cannot create a record b/c it is a
        # required field but for our test data I do not want to specify creators.
        if len(creators) == 0 and "pytest" not in sys.modules:
            raise Exception(f"Record has no creators: {self.title}\n{self.vault_url}")
        return creators

    @cached_property
    def custom_fields(self) -> dict[str, Any]:
        """Custom metadata fields. Custom fields are only popluated if we have something for them."""
        cf: dict[str, Any] = {}
        # 1) ArchivesSeries custom field, { series, subseries } dict
        if self.archives_series:
            cf["cca:archives_series"] = self.archives_series
        if self.course:
            cf["cca:course"] = self.course
        return cf

    @cached_property
    def dates(self) -> list[dict[str, Any]]:
        dates: list[dict[str, Any]] = []
        # https://inveniordm.docs.cern.ch/reference/metadata/#dates-0-n
        # _additional_ (non-publication) dates structured like
        # { "date": "EDTF lvl 0 date", type: { "id": "TYPE" }, "description": "free text" }
        # types: available, collected, copyrighted, created, other, submitted, updated, withdrawn
        # https://github.com/cca/cca_invenio/blob/main/app_data/vocabularies/date_types.yaml

        # dateCaptured
        for dc in self.etree.findall("./mods/origininfo/dateCaptured"):
            if dc.text:  # could be empty string
                dates.append(
                    {
                        "date": to_edtf(dc.text),
                        "type": {"id": "collected"},
                        "description": "date captured",
                    }
                )

        # we always have exactly one dateOtherWrapper and 0-1 dateOther, praise be
        date_other: Element | None = self.etree.find(
            "./mods/origininfo/dateOtherWrapper/dateOther"
        )
        if date_other is not None:
            date_other_type: str = date_other.get("type") or ""
            if date_other.text:
                dates.append(
                    {
                        "date": to_edtf(date_other.text),
                        "description": date_other_type.capitalize(),
                        "type": {"id": "other"},
                    }
                )
            else:
                # maybe we have a range with pointStart and pointEnd elements
                start: str | None = to_edtf(
                    self.etree.findtext("./mods/origininfo/dateOtherWrapper/pointStart")
                )
                end: str | None = to_edtf(
                    self.etree.findtext("./mods/origininfo/dateOtherWrapper/pointEnd")
                )
                if start and end:
                    dates.append(
                        {
                            "date": f"{start}/{end}",
                            "description": date_other_type.capitalize(),
                            "type": {"id": "other"},
                        }
                    )
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

        # TODO add artists books description

        # mods/relateditem[type=series] -> description[type=series-information]
        for series in self.etree.findall("./mods/relateditem[@type='series']"):
            title: str | None = series.findtext("./title")
            if title:
                desc.append(
                    {
                        "type": {
                            "id": "series-information",
                            "title": {"en": "Series information"},
                        },
                        "description": title.strip(),
                    }
                )

        # Art Collection notes are private so we skip further processing
        if self.vault_collection == art_collection_uuid:
            return desc

        # we have _many_ MODS note types & none map cleanly to Invenio description types
        for note in self.etree.findall("./mods/noteWrapper/note"):
            if note.text:
                note_type: str | None = note.get("type", "").capitalize()
                note_text: str = f"{note_type}: {note.text}" if note_type else note.text
                desc.append(
                    {
                        "type": {"id": "other", "title": {"en": "Other"}},
                        "description": note_text.strip(),
                    }
                )
        return desc

    @cached_property
    def formats(self) -> list[str]:
        formats: set[str] = set()
        for file in self.attachments:
            type = mimetypes.guess_type(file["name"], strict=False)[0]
            if type:
                formats.add(type)
        return list(formats)

    @cached_property
    def internal_notes(self) -> list[str]:
        # retain private art collection notes as internal_notes
        notes: list[str] = []
        if self.vault_collection == art_collection_uuid:
            for note in self.etree.findall("./mods/noteWrapper/note"):
                if note.text:
                    note_type: str | None = note.get("type", "").capitalize()
                    note_text: str = (
                        f"{note_type}: {note.text}" if note_type else note.text
                    )
                    notes.append(note_text)
        return notes

    @cached_property
    def publication_date(self) -> str | None:
        # date created, add other/additional dates to self.dates[]
        # level 0 EDTF date (YYYY,  YYYY-MM, YYYY-MM-DD or slash separated range between 2 of these)
        # https://inveniordm.docs.cern.ch/reference/metadata/#publication-date-1
        # mods/originfo/dateCreatedWrapper/dateCreated (note lowercase origininfo) or item.createdDate
        for origin_info in self.etree.findall("./mods/origininfo"):
            # use dateCreatedWrapper/dateCreated if we have it
            for dc_wrapper in origin_info.findall("./dateCreatedWrapper"):
                for date_created in dc_wrapper.findall("./dateCreated"):
                    # work around empty str or dict
                    if date_created.text:
                        edtf_date: str | None = to_edtf(date_created.text)
                        if edtf_date:
                            return edtf_date

                # maybe we have a range with pointStart and pointEnd elements?
                # edtf.text_to_edtf(f"{start}/{end}") returns None for valid dates so do in two steps
                start: str | None = to_edtf(dc_wrapper.findtext("./pointStart"))
                end: str | None = to_edtf(dc_wrapper.findtext("./pointEnd"))
                if start and end:
                    return f"{start}/{end}"

            # maybe we have mods/origininfo/semesterCreated, which is always a string (no children)
            semesterCreated: str | None = origin_info.findtext("./semesterCreated")
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
        for related_item in self.etree.findall("./mods/relatedItem"):
            title: str | None = related_item.findtext("./titleInfo/title")
            if title == "Design Book Review":
                issue_str: str | None = related_item.findtext("./part/detail/number")
                if issue_str:
                    # there are some double issues with numbers like 37/38
                    issue_no: int = int(issue_str[:2])
                    if issue_no < 19:
                        return "Design Book Review"
                    elif issue_no < 36:
                        return "MIT Press"
                    elif issue_no < 39:
                        return "Design Book Review"
                    else:
                        return "California College of the Arts"

        # 2) CCA/C archives has publisher info mods/originInfo/publisher
        # https://vault.cca.edu/items/c4583fe6-2e85-4613-a1bc-774824b3e826/1/%3CXML%3E
        # records have multiple originInfo nodes, might have an empty <publisher/> first
        for origin_info in self.etree.findall("./mods/originInfo"):
            publisher: str | None = origin_info.findtext("./publisher")
            if publisher:
                return publisher.strip()

        # 3) Press Clips items are not CCA but have only publication, not publisher, info
        # 4) Student work has no publisher
        return ""

    @cached_property
    def related_identifiers(self) -> list[dict[str, str | dict[str, str]]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#related-identifiersworks-0-n
        # Uses RDM_RECORDS_IDENTIFIERS_SCHEMES schemes e.g.
        # ARK, arXiv, Bibcode, DOI, EAN13, EISSN, Handle, IGSN, ISBN, ISSN, ISTC, LISSN, LSID, PubMed ID, PURL, UPC, URL, URN, W3ID
        # Relation types: https://github.com/inveniosoftware/invenio-rdm-records/blob/master/invenio_rdm_records/fixtures/data/vocabularies/relation_types.yaml
        # related_identifiers aren't indexed in the search engine, searches like
        # _exists_:metadata.related_identifiers returns items but metadata.related_identifiers:($URL) does not
        ri: list[dict[str, Any]] = []
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

        # Artists Books have mods/relateditem[type=isReferencedBy] for Koha link
        # Ex. https://vault.cca.edu/items/4d9d685c-9149-45e9-b7a3-e2f9e5ad0bd6/1/
        for related_item in self.etree.findall("./mods/relateditem"):
            # 3 types in VAULT: isReferencedBy, otherVersion, series
            type_to_relation_map: dict[str, str] = {
                "isReferencedBy": "ispartof",
                "otherVersion": "hasversion",
            }
            location = related_item.findtext("./location")
            relation_type: str | None = related_item.get("type")
            if location:
                url = get_url(location)
                if url and relation_type in type_to_relation_map:
                    ri.append(
                        {
                            "identifier": url,
                            "relation_type": {
                                "id": type_to_relation_map[relation_type]
                            },
                            "scheme": "url",
                        }
                    )

        # TODO there are other relations to add, like mods/relatedItem|relateditem
        # Example: https://vault.cca.edu/items/2a1bbc39-0619-4f95-8573-dcf4fd9c9e61/2/
        # but if a VAULT item is related to another VAULT item, we need to know both their new
        # IDs in Invenio to create the relation
        # Ex. https://vault.cca.edu/items/e507a72b-e318-4c42-b2ae-c7d4fb660a78/1/
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
        for rtype in self.etree.findall("./mods/typeOfResourceWrapper/typeOfResource"):
            if rtype.text in resource_type_map:
                return {"id": resource_type_map[rtype.text]}

        # TODO local/courseWorkType

        # physicalDescription/formBroad e.g. in Art Collection
        for formBroad in self.etree.findall("./mods/physicalDescription/formBroad"):
            if formBroad.text and formBroad.text in form_broad_map:
                return {"id": form_broad_map[formBroad.text]}

        # default to publication
        return {"id": "publication"}

    @cached_property
    def rights(self) -> list[dict[str, str | dict[str, str]]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#rights-licenses-0-n
        # Choices: https://github.com/cca/cca_invenio/blob/main/app_data/vocabularies/licenses.csv
        # We always have exactly one accessCondition node, str or dict
        for access_condition in self.etree.findall("./mods/accessCondition"):
            # if we have a href attribute prefer that
            href: str | None = access_condition.get("href")
            if href in license_href_map:
                return [{"id": license_href_map[href]}]

            # use substring matching—some long ACs contain the license name or URL
            if access_condition.text:
                for key in license_text_map.keys():
                    if key in access_condition.text:
                        return [{"id": license_text_map[key]}]

        # default to copyright
        return [{"id": "copyright"}]

    @cached_property
    def sizes(self) -> list[str]:
        # mods/physicalDescription/extent
        # https://inveniordm.docs.cern.ch/reference/metadata/#sizes-0-n
        extents: list[str] = []

        for extent in self.etree.findall("./mods/physicalDescription/extent"):
            if extent.text:
                extents.append(extent.text)

        # TODO there will be /local extent values in student work items
        return extents

    @cached_property
    def subjects(self) -> list[dict[str, str]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#subjects-0-n
        # Subjects are {id} or {subject} dicts
        # find_subjects pulls from mods/subject and mods/genreWrapper/genre
        subjects: set[Subject] = find_subjects(self.etree)
        # map formSpecific to naked keywords
        for form_specific in self.etree.findall(
            "./mods/physicalDescription/formSpecific"
        ):
            if form_specific.text:
                # type doesn't matter except for deduping against our real subjects
                # and "topic" is the most common in those
                subjects.add(Subject("topic", form_specific.text))
        return [s.to_invenio() for s in subjects]

    @cached_property
    def _is_artists_book(self) -> bool:
        # Item is in "Libraries eResources" collection & has formBroad artists books
        return (
            self.etree.findtext("./mods/physicalDescription/formBroad")
            == "artists' books (books)"
            and self.vault_collection == libraries_eresources_uuid
        )

    def get(self) -> dict[str, Any]:
        return {
            "access": self.access,
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
            "internal_notes": self.internal_notes,
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
                "description": self.abstracts[0] if len(self.abstracts) else "",
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
    records: list[dict[str, Any]] = []
    # we assume first arg is path to the item JSON
    for file in sys.argv[1:]:
        print(f"Processing file: {file}", file=sys.stderr)
        items = find_items(file)
        for item in items:
            r: Record = Record(item)
            records.append(r.get())
    # JSON pretty print record(s)
    json.dump(records, sys.stdout, indent=2)
