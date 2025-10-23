"""Parse names and lists of names from a variety of formats into {given_name,
family_name} or {name} (for organizations) dicts. This is used by
Record.creator only. It does not relate to the Invenio names.yaml vocabulary.
"""

import re

import spacy

nlp = spacy.load("en_core_web_lg")
# Force Spacy to recognize CSAC as only one ORG entity & not 2 separate ones
ruler = nlp.add_pipe("entity_ruler", config={"overwrite_ents": True}, after="ner")
patterns: list[dict[str, str]] = [
    {"label": "ORG", "pattern": "California School of Arts and Crafts"},
    # Other patterns we need to force recognition
    {"label": "ORG", "pattern": "Monir (or possibly Yonir)"},
    {"label": "PERSON", "pattern": "KR (Ken Rignal?)"},
]
ruler.add_patterns(patterns)  # type: ignore
nlp.select_pipes(enable=["ner", "entity_ruler"])


def ner(text: str) -> list[dict[str, str]]:
    # return a list of named PERSON or ORG entities from a string
    # https://spacy.io/usage/linguistic-features#named-entities
    doc = nlp(text)
    return [
        {"entity": e.text, "type": e.label_}
        for e in doc.ents
        if e.label_ in ("PERSON", "ORG")
    ]


def entity_to_name(entity: dict[str, str], namePart: str):
    if entity["type"] == "PERSON":
        return parse_name(entity["entity"])
    else:
        # default to organization
        return {"name": namePart}


def n(person_or_org: dict[str, str]) -> dict[str, str]:
    """add person/org type to name dict"""
    if (
        person_or_org.get("name")
        and type(person_or_org.get("given_name")) is not str
        and type(person_or_org.get("family_name")) is not str
    ):
        ntype: str = "organizational"
    # it's ok if person names are falsey, empty, but they must be strings
    elif (
        type(person_or_org.get("given_name")) is str
        and type(person_or_org.get("family_name")) is str
    ):
        ntype = "personal"
    else:
        raise Exception(
            f"Invalid name dict, has neither name nor family_name & given_name: {person_or_org}"
        )
    return {**person_or_org, "type": ntype}


def parse_name(namePart: str):
    """Parse wild variety of name strings into {given_name, family_name}
    or, if it looks like an organization name, return only {name}."""

    # semi-colon separated list of names
    if "; " in namePart:
        return [parse_name(p) for p in namePart.split("; ")]
    # there are two plus-separated lists of names in the data
    if " + " in namePart:
        return [parse_name(p) for p in namePart.split(" + ")]

    # usually Surname, Given Name but sometimes other things
    if "," in namePart:
        # last, first
        parts = namePart.split(", ")
        if len(parts) == 2:
            # other than a few org names with place parentheticals, these are names
            if "Calif.)" in namePart:
                return n({"name": namePart})
            return n({"given_name": parts[1], "family_name": parts[0]})
        # name with a DOB/death date string after a second comma
        if len(parts) == 3 and re.match(r"[0-9]{4}\-([0-9]{4})?", parts[2].strip()):
            return n({"given_name": parts[1], "family_name": parts[0]})
        # two or more commas, maybe we have a comma-separated list of names?
        if len(parts) > 2:
            entities: list[dict[str, str]] = ner(namePart)
            if len(entities) == 0:
                # weird, no entities, assume organization
                return n({"name": namePart})
            if len(entities) == 1:
                # just one entity, easy, assume the NER type inference is correct
                return entity_to_name(entities[0], namePart)
            if len(entities) > 1:
                # if we have more than one PERSON entity, assume we have a list of names
                if len([e for e in entities if e["type"] == "PERSON"]) > 1:
                    return [parse_name(p) for p in parts]
                # multiple entities of mixed types
                raise Exception(
                    f'Found multiple entities of different types in namePart "{namePart}": {entities}'
                )
    # split on spaces, often "Givenname Surname", but multiple spaces is where it gets tricky
    else:
        # various CCA(C) org names are easily mistaken for personal names
        if re.match(r"\bCCAC?", namePart):
            return n({"name": namePart})
        parts = namePart.split(" ")
        if len(parts) == 1:
            # looks like an organization name
            return n({"name": namePart})
        if len(parts) == 2:
            return n({"given_name": parts[0], "family_name": parts[1]})
        if len(parts) > 2:
            # could be "First Second Third" name or an organization
            entities: list[dict[str, str]] = ner(namePart)
            if len(entities) == 0:
                # no entities, most likely an organization
                return n({"name": namePart})
            elif len(entities) == 1 and entities[0]["type"] == "PERSON":
                return n({"given_name": " ".join(parts[0:2]), "family_name": parts[2]})
            elif len(entities) == 1 and entities[0]["type"] == "ORG":
                return n({"name": namePart})
            # more than one entity but they're all PERSON, assume one name
            elif len(entities) > 1 and len(
                [e for e in entities if e["type"] == "PERSON"]
            ) == len(entities):
                num_parts: int = len(parts)
                return n(
                    {
                        "given_name": " ".join(parts[0 : (num_parts - 1)]),
                        "family_name": parts[num_parts - 1],
                    }
                )
            else:
                # multiple entities of different types, no comma so it's not a list
                raise Exception(
                    f'Found multiple entities of different types in namePart "{namePart}": {entities}'
                )
