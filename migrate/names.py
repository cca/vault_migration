import re

import spacy

nlp = spacy.load("en_core_web_lg")
nlp.select_pipes(enable=["ner"])


def ner(str):
    # return a list of named PERSON or ORG entities from a string
    # https://spacy.io/usage/linguistic-features#named-entities
    doc = nlp(str)
    return [
        {"entity": e.text, "type": e.label_}
        for e in doc.ents
        if e.label_ in ("PERSON", "ORG")
    ]


def entity_to_name(entity, namePart):
    if entity["type"] == "PERSON":
        return parse_name(entity["entity"])
    else:
        # default to organization
        return {"name": namePart}


def parse_name(namePart):
    """parse wild variety of name strings into {givename, familyname}
    or, if it looks like an orgnaization name, return only {name}"""

    # semi-colon separated list of names
    if "; " in namePart:
        return [parse_name(p) for p in namePart.split("; ")]
    # there are two plus-separated lists of names in the data
    if " + " in namePart:
        return [parse_name(p) for p in namePart.split(" + ")]

    # usually Surname, Givenname but sometimes other things
    if "," in namePart:
        # last, first
        parts = namePart.split(", ")
        if len(parts) == 2:
            # other than a few org names with place parentheticals, these are names
            if "Calif.)" in namePart:
                return {"name": namePart}
            return {"given_name": parts[1], "family_name": parts[0]}
        # name with a DOB/dath date string after a second comma
        if len(parts) == 3 and re.match(r"[0-9]{4}\-([0-9]{4})?", parts[2].strip()):
            return {"given_name": parts[1], "family_name": parts[0]}
        # two or more commas, maybe we have a comma-separated list of names?
        if len(parts) > 2:
            entities = ner(namePart)
            if len(entities) == 0:
                # weird, no entities, assume organization
                return {"name": namePart}
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
            return {"name": namePart}
        parts = namePart.split(" ")
        if len(parts) == 1:
            # looks like an organization name
            return {"name": namePart}
        if len(parts) == 2:
            return {"given_name": parts[0], "family_name": parts[1]}
        if len(parts) > 2:
            # could be "First Second Third" name or an organization
            entities = ner(namePart)
            if len(entities) == 0:
                # no entities, most likely an organization
                return {"name": namePart}
            elif len(entities) == 1 and entities[0]["type"] == "PERSON":
                return {"given_name": " ".join(parts[0:2]), "family_name": parts[2]}
            elif len(entities) == 1 and entities[0]["type"] == "ORG":
                return {"name": namePart}
            # more than one entity but they're all PERSON, assume one name
            elif len(entities) > 1 and len(
                [e for e in entities if e["type"] == "PERSON"]
            ) == len(entities):
                l = len(parts)
                return {
                    "given_name": " ".join(parts[0 : (l - 1)]),
                    "family_name": parts[l - 1],
                }
            else:
                # multiple entities of different types, no comma so it's not a list
                raise Exception(
                    f'Found multiple entities of different types in namePart "{namePart}": {entities}'
                )
