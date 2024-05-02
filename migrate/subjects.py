#!/usr/bin/env python
# extract subjects from VAULT metadata
# meant to be run like: python e.py *.json
import csv
import sys

import xmltodict

from utils import find_items, mklist


# hashable subject
class Subject:
    def __init__(self, type, value, auth="") -> None:
        self.type = type.title()
        self.value = value
        # auths we use: 'LC', 'LOCAL', 'LC-NACO', 'ULAN', 'LCSH', 'AAT'
        self.authority = auth.upper()

    def __hash__(self):
        return hash((self.type, self.value, self.authority))

    def __eq__(self, other):
        return (
            self.type == other.type
            and self.value == other.value
            and self.authority == other.authority
        )

    def __str__(self):
        repr = f"{self.type}: {self.value}"
        if self.authority:
            repr += f" ({self.authority})"
        return repr

    # sorting
    def __lt__(self, other):
        return (self.type, self.value) < (other.type, other.value)


# types from under mods/subject
TYPES = [
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
    mods = xml.get("xml", {}).get("mods", {})
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
    subjects = set()
    for file in sys.argv:
        for item in find_items(file):
            xml = xmltodict.parse(item["metadata"])
            subjects.update(find_subjects(xml))

    # print sorted subjects
    for s in sorted(subjects):
        print(s)
