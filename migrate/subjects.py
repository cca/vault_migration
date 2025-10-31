#!/usr/bin/env python
# extract subjects from VAULT metadata
# can be imported or run like: python subjects.py *.json
import json
import sys
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from utils import find_items

# subjects map JSON sits in the same directory
subjects_map: dict[str, str] | Literal[False] = False
current_file_path: Path = Path(__file__).resolve()
current_directory: Path = current_file_path.parent
file_path: Path = current_directory / "subjects_map.json"
if file_path.exists():
    with open(file_path) as f:
        subjects_map = json.load(f)


# hashable subject
class Subject:
    def __init__(self, type, value, auth="") -> None:
        self.type: str = type.title()
        self.value: str = value
        # auths in VAULT: 'LC', 'LOCAL', 'LC-NACO', 'ULAN', 'LCSH', 'AAT'
        self.authority: str = auth.upper()

    def __hash__(self) -> int:
        return hash((self.type, self.value, self.authority))

    def __eq__(self, other) -> bool:
        return (
            self.type == other.type
            and self.value == other.value
            and self.authority == other.authority
        )

    def __repr__(self) -> str:
        return f"Subject({self.__str__()})"

    def __str__(self) -> str:
        repr: str = f"{self.type}: {self.value}"
        if self.authority:
            repr += f" ({self.authority})"
        return repr

    # sorting
    def __lt__(self, other) -> bool:
        return (self.type, self.value) < (other.type, other.value)

    def to_invenio(self) -> dict[str, str]:
        # Returns either { id: invenio subj id in map } or { subject: term }
        # Temporal IDs are just the term
        if self.type == "Temporal":
            return {"id": self.value}

        if not subjects_map:
            raise Exception(
                "subjects_map.json not found, unable to convert Subject to Invenio format"
            )
        if self.value.lower() in subjects_map:
            return {"id": subjects_map[self.value.lower()]}
        return {"subject": self.value}


# types from under mods/subject
SUBJECT_TYPES: list[str] = [
    "geographic",
    "topic",
    "name",
    "topicCona",
    "temporal",
]


def find_subjects(xml: Element) -> set[Subject]:
    """Takes an ElementTree and looks for subjects in mods/subject and mods/genreWrapper/genre"""
    subjects: set[Subject] = set()
    for mods_subject in xml.findall("./mods/subject"):
        for t in SUBJECT_TYPES:  # check for every subject type
            for subject in mods_subject.findall(f"./{t}"):
                if subject.text:
                    authority: str = subject.get("authority") or ""
                    real_type: str = t if t != "topicCona" else "topic"
                    subjects.add(Subject(real_type, subject.text, authority))

    for wrapper in xml.findall("./mods/genreWrapper"):
        for genre in wrapper.findall("./genre"):
            if genre.text:
                authority: str = genre.get("authority") or ""
                subjects.add(Subject("genre", genre.text, authority))

    # Treat physicalDescription forms as genres, we have no auths for these
    for form in xml.findall("./mods/physicalDescription/formBroad"):
        if form.text:
            subjects.add(Subject("genre", form.text))
    for form in xml.findall("./mods/physicalDescription/formSpecific"):
        if form.text:
            subjects.add(Subject("genre", form.text))

    return subjects


if __name__ == "__main__":
    # CLI usage: python migrate/subjects.py vm/json/*.json
    # Prints a list of subjects found in the metadata
    subjects: set[Subject] = set()
    for file in sys.argv:
        for item in find_items(file):
            xml: Element = ElementTree.fromstring(item["metadata"])
            subjects.update(find_subjects(xml))

    # print sorted subjects
    for s in sorted(subjects):
        print(s, s.to_invenio())
