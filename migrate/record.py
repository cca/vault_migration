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
    cca_affiliation,
    collection_uuids,
    extent_page_range,
    find_items,
    get_url,
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
        # we default to restricted but set certain collections public
        access: dict[str, Literal["public", "restricted"]] = {
            "files": "restricted",
            "record": "restricted",
        }
        view_level: str | None = self.etree.findtext("./local/viewLevel")
        if (
            view_level
            and view_level.strip().lower() == "public"
            or self.vault_collection
            in [
                collection_uuids["faculty_research"],
                collection_uuids["oa"],
            ]
        ):
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
            for part_number in titleinfo.findall("partNumber"):
                if part_number.text:
                    atitles.append(
                        {
                            "title": f"Number: {part_number.text}",
                            "type": {"id": "other"},
                        }
                    )
        return atitles

    @cached_property
    def archives_series(self) -> dict[str, str] | None:
        series: str | None = self.etree.findtext("./local/archivesWrapper/series")
        if series and series not in archives_series_vocab:
            # Inconsistency but it doesn't rise to the point of an Exception
            print(
                f'Warning: "{series}" is not in CCA/C Archives Series',
                file=sys.stderr,
            )
        subseries: str | None = self.etree.findtext("./local/archivesWrapper/subseries")
        if (
            subseries
            and series
            and subseries not in archives_series_vocab.get(series, [])
        ):
            print(
                f'Warning: Archives subseries "{subseries}" not found under series "{series}"',
                file=sys.stderr,
            )
        if series and not subseries:
            print(f"Archives series w/o subseries: {self.vault_url}", file=sys.stderr)
        # ? Should we only return values if they're in the vocab?
        if series and subseries:
            return {"series": series, "subseries": subseries}
        return {}

    @cached_property
    def course(self) -> dict[str, Any] | None:
        course_info: Element | None = self.etree.find("./local/courseInfo")
        if course_info is not None and any(s for s in course_info.itertext() if s):
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
        Libraries AND Mudflats).

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

                    names: list[dict[str, str]] = parse_name(name_part_text)
                    if creator.get("role") or len(creator.get("affiliations", [])):
                        # if we have role/affiliation, we can only handle single names
                        if len(names) > 1:
                            raise Exception(
                                f"Unexpected mods/name structure: parse_name(namePart) returned multiple names but we also have role/affiliation.\nName text: {' '.join([t for t in name_element.itertext()])}\n{self.vault_url}"
                            )
                        creators.append(
                            {
                                "affiliations": creator["affiliations"],
                                "person_or_org": names[0],
                                "role": creator["role"],
                            }
                        )
                    else:
                        # no role/affiliation, add all names
                        creators.extend([{"person_or_org": name} for name in names])
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
                        # parse_name now always returns a list
                        creators.extend(
                            [
                                {"person_or_org": name}
                                for name in parse_name(name_part.text)
                            ]
                        )

        # Syllabi: we have no mods/name but list faculty in courseInfo/faculty
        if len(creators) == 0:
            faculty: str | None = self.etree.findtext("./local/courseInfo/faculty")
            if faculty:
                creators.extend(
                    [
                        {
                            "affiliations": cca_affiliation,
                            "person_or_org": name,
                            "role": {"id": "creator"},
                        }
                        for name in parse_name(faculty)
                    ]
                )

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
                creators.extend(
                    [
                        {
                            "person_or_org": name,
                        }
                        for name in parse_name(author)
                    ]
                )

        # If we _still_ have no creators, log a warning & use [Unknown]
        if len(creators) == 0:
            print(
                f"Record has no creators: {self.title}\n{self.vault_url}",
                file=sys.stderr,
            )
            creators.append(
                {
                    "person_or_org": {
                        "family_name": "[Unknown]",
                        "given_name": "",
                        "type": "personal",
                    },
                }
            )
        return creators

    @cached_property
    def custom_fields(self) -> dict[str, Any]:
        """Custom metadata fields. Custom fields are only popluated if we have something for them.
        If we add a custom field which is not configured in Invenio, it is dropped from the record
        without an error."""
        cf: dict[str, Any] = {}
        # 1) ArchivesSeries custom field, { series, subseries } dict
        if self.archives_series:
            cf["cca:archives_series"] = self.archives_series
        if self.course:
            cf["cca:course"] = self.course
        if self.journal:
            cf["journal:journal"] = self.journal
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

        descriptions: list[dict[str, Any]] = []
        if len(self.abstracts) > 1:
            descriptions.extend(
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
                descriptions.append(
                    {
                        "type": {
                            "id": "series-information",
                            "title": {"en": "Series information"},
                        },
                        "description": title.strip(),
                    }
                )

        for name_desc in self.etree.findall("./mods/name/subNameWrapper/description"):
            if name_desc.text:
                descriptions.append(
                    {
                        "type": {"id": "other", "title": {"en": "Other"}},
                        "description": f"Creator note: {name_desc.text.strip()}",
                    }
                )

        for note in self.etree.findall("./mods/physicalDescriptionNote/note"):
            if note.text:
                note_type: str = note.get("type", "").capitalize()
                note_text: str = f"{note_type}: {note.text}" if note_type else note.text
                descriptions.append(
                    {
                        "type": {"id": "other", "title": {"en": "Other"}},
                        "description": note_text.strip(),
                    }
                )

        # Parent book title for Fac Research book chapter)
        if (
            self.vault_collection == collection_uuids["faculty_research"]
            and self.etree.findtext("./mods/genreWrapper/genre") == "book chapter"
        ):
            host_item: Element | None = self.etree.find(
                "./mods/relatedItem[@type='host']"
            )
            if host_item is not None:
                book_title: str | None = host_item.findtext("./title")
                if book_title:
                    desc_text: str = f"Published in <i>{book_title.strip()}</i>"
                    pages: str | None = extent_page_range(host_item)
                    if pages:
                        desc_text += f", pages {pages}"
                    desc_text += "."
                    descriptions.append(
                        {
                            "type": {
                                # series or other? Series is closer but misleading
                                "id": "series-information",
                                "title": {"en": "Series information"},
                            },
                            "description": desc_text,
                        }
                    )

        # Art Collection notes are private so we skip further processing
        # ! This comes AFTER other processing but BEFORE noteWrapper below
        if self.vault_collection == collection_uuids["art_collection"]:
            return descriptions

        # we have _many_ MODS note types & none map cleanly to Invenio description types
        for note in self.etree.findall("./mods/noteWrapper/note"):
            if note.text:
                note_type = note.get("type", "").capitalize()
                note_text: str = f"{note_type}: {note.text}" if note_type else note.text
                descriptions.append(
                    {
                        "type": {"id": "other", "title": {"en": "Other"}},
                        "description": note_text.strip(),
                    }
                )
        return descriptions

    @cached_property
    def formats(self) -> list[str]:
        formats: set[str] = set()
        for file in self.attachments:
            mtype: str | None = mimetypes.guess_type(file["name"], strict=False)[0]
            if mtype:
                formats.add(mtype)
        return list(formats)

    @cached_property
    def internal_notes(self) -> list[str]:
        # retain private art collection notes as internal_notes
        notes: list[str] = []
        if self.vault_collection == collection_uuids["art_collection"]:
            for note in self.etree.findall("./mods/noteWrapper/note"):
                if note.text:
                    note_type: str | None = note.get("type", "").capitalize()
                    note_text: str = (
                        f"{note_type}: {note.text}" if note_type else note.text
                    )
                    notes.append(note_text)
        return notes

    @cached_property
    def journal(self) -> dict[str, str] | None:
        # mods/relatedItem[@type="host"] -> journal custom field
        # https://inveniordm.docs.cern.ch/reference/metadata/#journal-0-1
        # Confirm item is article before assuming the meaning of relatedItem elements
        article_types: set[str] = {"article", "journal article"}
        genres: set[str | None] = {
            self.etree.findtext("./mods/genre"),
            self.etree.findtext("./mods/genreWrapper/genre"),
        }
        if genres.intersection(article_types):
            for related_item in self.etree.findall("./mods/relatedItem"):
                if related_item.get("type") == "host":
                    journal: dict[str, str] = {}
                    # DBR uses titleInfo/title, Faculty Research uses title
                    title: str | None = related_item.findtext(
                        "./title"
                    ) or related_item.findtext("./titleInfo/title")
                    if title:
                        journal["title"] = title.strip()
                    issn: str | None = None
                    for identifier in related_item.findall("./identifier"):
                        id_type: str | None = identifier.get("type")
                        id_text: str | None = identifier.text
                        if id_type and id_text and id_type.lower() == "issn":
                            issn = id_text.strip()
                            journal["issn"] = issn
                    for detail in related_item.findall("./part/detail"):
                        detail_type: str | None = detail.get("type")
                        if detail_type == "volume":
                            volume: str | None = detail.findtext("./number")
                            if volume:
                                journal["volume"] = volume.strip()
                        elif detail_type == "number":
                            issue: str | None = detail.findtext("./number")
                            if issue:
                                journal["issue"] = issue.strip()
                    pages: str | None = extent_page_range(related_item)
                    if pages:
                        journal["pages"] = pages
                    if journal:
                        return journal
        return None

    @cached_property
    def locations(self) -> list[dict[str, str]]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#locations-0-n
        locations: list[dict[str, str]] = []
        for loc_el in self.etree.findall("./mods/location"):
            location: dict[str, str] = {}
            physical_loc: str | None = loc_el.findtext("./physicalLocation")
            if physical_loc:
                location["place"] = physical_loc.strip()
            sublocation: str | None = loc_el.findtext("./copyInformation/sublocation")
            sublocation_detail: str | None = loc_el.findtext(
                "./copyInformation/sublocationDetail"
            )
            shelf: str | None = loc_el.findtext("./copyInformation/shelfLocator")
            copy_info_strings: list[str] = []
            if sublocation:
                copy_info_strings.append(f"Building: {sublocation.strip()}")
            if sublocation_detail:
                copy_info_strings.append(f"Area: {sublocation_detail.strip()}")
            if shelf:
                copy_info_strings.append(f"Shelf: {shelf.strip()}")
            if len(copy_info_strings):
                location["description"] = ". ".join(copy_info_strings) + "."
            if location:
                locations.append(location)
        return locations

    @cached_property
    def publication_date(self) -> str | None:
        # date created, add other/additional dates to self.dates[]
        # level 0 EDTF date (YYYY,  YYYY-MM, YYYY-MM-DD or slash separated range between 2 of these)
        # https://inveniordm.docs.cern.ch/reference/metadata/#publication-date-1
        # mods/originfo/dateCreatedWrapper/dateCreated (note lowercase origininfo) or item.createdDate
        # Note: code takes _the last_ date found below, change if that's a problem
        edtf_date: str | None = None
        for origin_info in self.etree.findall("./mods/origininfo"):
            # use dateCreatedWrapper/dateCreated if we have it
            for dc_wrapper in origin_info.findall("./dateCreatedWrapper"):
                for date_created in dc_wrapper.findall("./dateCreated"):
                    # work around empty str or dict
                    if date_created.text:
                        edtf_date = to_edtf(date_created.text)

                # maybe we have a range with pointStart and pointEnd elements?
                # edtf.text_to_edtf(f"{start}/{end}") returns None for valid dates so do in two steps
                start: str | None = to_edtf(dc_wrapper.findtext("./pointStart"))
                end: str | None = to_edtf(dc_wrapper.findtext("./pointEnd"))
                if start and end:
                    edtf_date = f"{start}/{end}"

            # maybe we have mods/origininfo/semesterCreated, which is always a string (no children)
            semesterCreated: str | None = origin_info.findtext("./semesterCreated")
            if semesterCreated:
                edtf_date = to_edtf(semesterCreated)

        # mods/relatedItem/part/date for Faculty Research items
        for rel_item_date in self.etree.findall("./mods/relatedItem/part/date"):
            if rel_item_date.text:
                edtf_date = to_edtf(rel_item_date.text)

        # fall back on when the VAULT record was made (item.createdDate)
        if edtf_date:
            return edtf_date
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
        ri: list[dict[str, Any]] = []

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

        # Artists Books have mods/relateditem (lowercase) @type=isReferencedBy for Koha link
        # https://vault.cca.edu/items/4d9d685c-9149-45e9-b7a3-e2f9e5ad0bd6/1/%3CXML%3E
        # Other Libraries items have mods/relateditem too
        # https://vault.cca.edu/items/e507a72b-e318-4c42-b2ae-c7d4fb660a78/1/%3CXML%3E
        # https://vault.cca.edu/items/2a1bbc39-0619-4f95-8573-dcf4fd9c9e61/2/%3CXML%3E
        for related_item in self.etree.findall("./mods/relateditem"):
            # 3 types in VAULT: isReferencedBy, otherVersion, series
            type_to_relation_map: dict[str, str] = {
                "isReferencedBy": "isreferencedby",
                "otherVersion": "hasversion",
            }
            location: str | None = related_item.findtext("./location")
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

        # DBR & Faculty Research have relatedItem (uppercase) @type=host with ISSN/ISBN
        # https://vault.cca.edu/items/71b4c22c-4326-4753-8f34-439578cc285c/1/%3CXML%3E
        # https://vault.cca.edu/items/439a3ea3-7a3c-4f4f-9a4e-fddd83ca2f5f/5/%3CXML%3E
        for related_item in self.etree.findall("./mods/relatedItem"):
            relation_type: str | None = related_item.get("type")
            if relation_type == "host":
                for identifier in related_item.findall("./identifier"):
                    id_type: str | None = identifier.get("type")
                    id_text: str | None = identifier.text
                    if id_type and id_text:
                        if id_type.lower() == "issn":
                            ri.append(
                                {
                                    "identifier": id_text,
                                    "relation_type": {"id": "ispublishedin"},
                                    "scheme": "issn",
                                }
                            )
                        elif id_type.lower() == "isbn":
                            ri.append(
                                {
                                    "identifier": id_text,
                                    "relation_type": {"id": "ispublishedin"},
                                    "scheme": "isbn",
                                }
                            )

        # Faculty Research has mods/identifier[@type=DOI]
        # https://vault.cca.edu/items/50a21768-ca40-4faa-bb7d-36938d63cb72/1/%3CXML%3E
        for identifier in self.etree.findall("./mods/identifier"):
            id_type: str | None = identifier.get("type")
            id_text: str | None = identifier.text
            if id_type and id_text and id_type.lower() == "doi":
                ri.append(
                    {
                        "identifier": id_text.strip(),
                        "relation_type": {"id": "isidenticalto"},
                        "scheme": "doi",
                    }
                )

        # mods/location/url used in multiple places including Faculty Research
        # https://vault.cca.edu/items/3bf05a46-a6f5-44df-adf7-d24bf2fbedcf/2/%3CXML%3E
        for location_url in self.etree.findall("./mods/location/url"):
            url_text: str | None = location_url.text
            if url_text:
                url: str | None = get_url(url_text)
                if url:
                    ri.append(
                        {
                            "identifier": url,
                            "relation_type": {"id": "isidenticalto"},
                            "scheme": "url",
                        }
                    )

        # Add a URL identifier for the old VAULT item
        # To search for a VAULT item's Invenio record, we have to escape many characters like:
        # metadata.related_identifiers.identifier:https\:\/\/vault\.cca\.edu\/items\/...
        if self.vault_url:
            ri.append(
                {
                    "identifier": self.vault_url,
                    "relation_type": {"id": "isnewversionof"},
                    "scheme": "url",
                }
            )
        return ri

    @cached_property
    def resource_type(self) -> dict[str, str]:
        # https://inveniordm.docs.cern.ch/reference/metadata/#resource-type-1
        # https://github.com/cca/cca_invenio/blob/main/app_data/vocabularies/resource_types.yaml
        # There are many fields that could be used to determine the resource type. Priority:
        # 1. mods/typeOfResource, 2. local/courseWorkType, 3. TBD (there are more...)
        # mods/typeOfResourceWrapper/typeOfResource

        # Syllabus Collection only contains syllabi
        if self.vault_collection == collection_uuids["syllabus_collection"]:
            return {"id": "publication-syllabus"}

        # Faculty Research has type in genreWrapper/genre
        if self.vault_collection == collection_uuids["faculty_research"]:
            for genre in self.etree.findall("./mods/genreWrapper/genre"):
                if genre.text in resource_type_map:
                    return {"id": resource_type_map[genre.text]}

        # OA Journal Articles has type in genre
        if self.vault_collection == collection_uuids["oa"]:
            for genre in self.etree.findall("./mods/genre"):
                if genre.text in resource_type_map:
                    return {"id": resource_type_map[genre.text]}

        # Take the first typeOfResource value we find
        for rtype in self.etree.findall("./mods/typeOfResourceWrapper/typeOfResource"):
            if rtype.text in resource_type_map:
                return {"id": resource_type_map[rtype.text]}

        # TODO local/courseWorkType

        # physicalDescription/formBroad e.g. in Art Collection
        for formBroad in self.etree.findall("./mods/physicalDescription/formBroad"):
            if formBroad.text in form_broad_map:
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
        return [s.to_invenio() for s in subjects]

    @cached_property
    def _is_artists_book(self) -> bool:
        # Item is in "Libraries eResources" collection & has formBroad artists books
        return (
            self.etree.findtext("./mods/physicalDescription/formBroad")
            == "artists' books (books)"
            and self.vault_collection == collection_uuids["libraries_eresources"]
        )

    def get(self) -> dict[str, Any]:
        return {
            "access": self.access,
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
                "locations": {"features": self.locations},
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
