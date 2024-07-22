# This script takes a CSV export of our VAULT Subjects & Genres sheet
# https://docs.google.com/spreadsheets/d/1la_wsFPOkHLjpv4-f3tWwMsCd0_xzuqZ5xp_p1zAAoA/edit#gid=1465207925
# and converts it into three files:
# - subjects_map.json: a mapping of VAULT subject strings to Invenio subject IDs
# - cca_local.yaml: a YAML file of CCA Local subjects
# - lc.yaml: a YAML file of Library of Congress subjects (from multiple authorities)
#
# Usage:
# python migrate/mk_subjects.py subjects.csv
# It is meant to be run from the project root like this. It takes additional static vocabularies we made
# in the "vocabs" dir and includes them in the cca_local subject. The 2 YAML files are written to the
# vocab directory and the JSON file is written to the migrate directory.
import csv
import json
from pathlib import Path
import sys
import uuid

import yaml


def get_uuid(term: str) -> str:
    # TODO use real identifiers, NS_URL chosen b/c there's no ideal option
    return str(uuid.uuid5(uuid.NAMESPACE_URL, term))


def dump_all(subjects_map, cca_local, lc):
    with open("migrate/subjects_map.json", "w") as file:
        json.dump(subjects_map, file, indent=2)
    with open("vocab/cca_local.yaml", "w") as file:
        yaml.dump(cca_local, file)
    with open("vocab/lc.yaml", "w") as file:
        yaml.dump(lc, file)


def main(file: str):
    with open(file, "r") as fp:
        subjects_map: dict[str, str] = {}
        cca_local: list[dict[str, str]] = []
        lc: list[dict[str, str]] = []

        reader = csv.DictReader(fp)
        for row in reader:
            auth: str = row["Auth"]
            status: str = row["Status"].lower()  # omit, combine, done, problem
            term: str = row["New Value"] if row["New Value"] else row["VAULT value"]
            subject: dict[str, str] = {"subject": term}

            if status in ("omit", "problem", ""):
                continue

            if auth.upper() == "LOCAL":
                # Combined local subjects _must_ have a new value
                if status == "combine":
                    if not row["New Value"]:
                        raise ValueError(
                            f"Combined local subject without a New Value: {term}"
                        )
                subject["id"] = get_uuid(term)
                subject["scheme"] = "cca_local"

            # ULAN subjects are added to cca_local but with their ULAN URI as the ID
            if auth.upper() == "ULAN":
                if not row["Auth URI"]:
                    raise ValueError(
                        f"No Auth URI for ULAN subject: {term}\nAll ULAN subjects must have an Auth URI."
                    )
                subject["id"] = row["Auth URI"]
                subject["scheme"] = "cca_local"

            # Covers multiple LC authorities: LCNAF, LCSH, LCGFT
            elif auth.upper().startswith("LC"):
                if not row["Auth URI"]:
                    raise ValueError(
                        f"No Auth URI for LC subject: {term} ({auth})\nAll LC subjects must have an Auth URI."
                    )
                subject["id"] = row["Auth URI"]
                subject["scheme"] = "lc"

            subjects_map[row["VAULT value"].lower()] = subject["id"]
            # combined terms are not added to the final vocab files (but are in the map)
            if status == "done":
                locals()[subject["scheme"]].append(subject)

        # premade sub-vocabs to be added to cca_local
        for filename in [
            "subject_names.yaml",
            "programs.yaml",
        ]:  # TODO: archives series
            with open(Path("vocab") / filename, "r") as fh:
                terms = yaml.load(fh, Loader=yaml.FullLoader)
                for term in terms:
                    assert type(term) == dict  # solely for type hinting
                    # if term has already been added to the subjects_map, skip it
                    if (term_text := term["subject"].lower()) in subjects_map:
                        continue
                    # assign an ID that matches what we have in the map from combined subjects.csv terms
                    term["id"] = get_uuid(term["subject"])
                    subjects_map[term_text] = term["id"]
                    locals()[term["scheme"]].append(term)

        dump_all(subjects_map, cca_local, lc)


if __name__ == "__main__":
    main(sys.argv[1])
