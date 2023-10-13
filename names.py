""" Convert EQUELLA taxonomy export into Invenio names vocab
https://inveniordm.docs.cern.ch/customize/vocabularies/names/
TODO: CCA affiliations? We would have to manually add or use item records
"""
import argparse
import json

import yaml


def convert(term):
    """convert EQUELLA personal names taxo term into Invenio name

    Args:
        term (dict): { "term": "Wang, Wayne, 1949-", "fullTerm": "oclc\\personal\\Wang, Wayne, 1949-", }

    Returns:
        dict: { "family_name": "Wang", "given_name": "Wayne" }
    """
    # names vocab supports identifiers but we have no URIs, have to look them up manually
    # we do assume no one has a comma in their name
    # Some names were entered improperly, without commas
    if "," in term["term"]:
        name_split = term["term"].split(",")
        name = {
            "family_name": name_split[0].strip(),
            "given_name": name_split[1].strip(),
        }
    elif " " in term["term"]:
        name_split = term["term"].split(" ")
        name = {
            "family_name": name_split[0].strip(),
            "given_name": " ".join(name_split[1:]).strip(),
        }
    else:
        raise Exception(
            f'Unable to parse given and family names for name "${term["term"]}"'
        )
    return name


def main(args):
    with args.file:
        terms = json.load(args.file)

    names = [convert(term) for term in terms]

    with open("vocab/names.yaml", "w") as f:
        yaml.dump(names, f, allow_unicode=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert our Libraries subject name taxonomy in VAULT to Invenio names.yaml vocabulary"
    )
    parser.add_argument(
        "file",
        default="taxos/subject-name-complete.json",
        help="Path to JSON taxonomy",
        nargs="?",
        type=argparse.FileType("r"),
    )
    args = parser.parse_args()
    main(args)
