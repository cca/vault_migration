#!/usr/bin/env python
# extract subjects from VAULT metadata
# can be imported or run like: python subjects.py *.json
import json
from pathlib import Path
import sys
from typing import Literal

import xmltodict

from utils import find_items, mklist

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
TYPES: list[str] = [
    "geographic",
    "topic",
    "name",
    "topicCona",
    "temporal",
]


def subjects_from_xmldict(type: str, tree: dict | str) -> list[Subject]:
    # takes xmltodict of mods/subject or mods/genreWrapper/genre
    # and returns a deduped list of Subject objects

    # treat topicCona as topic
    if type == "topicCona":
        type = "topic"

    if isinstance(tree, str):
        return [Subject(type, tree)]

    subjects = set()
    for s in mklist(tree):
        if isinstance(s, dict):
            auth = s.get("@authority", "")
            s = s.get("#text")
        if s:  # empty tag like <name/> -> s = None
            subjects.add(Subject(type, s, auth))
    return list(subjects)


def find_subjects(xml: dict) -> set[Subject]:
    # looks for subjects in mods/subject and mods/genreWrapper/genre
    subjects = set()
    # work from either root or <xml> starting point
    xml = xml.get("xml", xml)
    mods = xml.get("mods", {})
    for s in mklist(mods.get("subject")):
        if s:  # empty <subject/> alongside actual ones will be None
            for t in TYPES:  # check for every subject type
                for sub in mklist(s.get(t)):
                    subjects.update(subjects_from_xmldict(t, sub))

    for wrapper in mklist(mods.get("genreWrapper", {})):
        for genre in mklist(wrapper.get("genre")):
            subjects.update(subjects_from_xmldict("genre", genre))
    return subjects


if __name__ == "__main__":
    # CLI usage: python migrate/subjects.py vm/json/*.json
    # Prints a list of subjects found in the metadata
    subjects: set[Subject] = set()
    for file in sys.argv:
        for item in find_items(file):
            xml = xmltodict.parse(item["metadata"])
            subjects.update(find_subjects(xml))

    # print sorted subjects
    for s in sorted(subjects):
        print(s, s.to_invenio())
