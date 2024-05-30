# This script takes a CSV export of our VAULT Subjects & Genres sheet
# https://docs.google.com/spreadsheets/d/1la_wsFPOkHLjpv4-f3tWwMsCd0_xzuqZ5xp_p1zAAoA/edit#gid=1465207925
# and converts it into three files:
# - subjects_map.json: a mapping of VAULT subject strings to Invenio subject IDs
# - cca_local.yaml: a YAML file of CCA Local subjects
# - lc.yaml: a YAML file of Library of Congress subjects (from multiple authorities)
#
# Usage:
# python migrate/convert_subjects.py subjects.csv
# It is meant to be run from the project root like this. The 2 YAML files are written to the vocab directory
# and the JSON file is written to the migrate directory.
import csv
from io import TextIOWrapper
import json
import sys
from typing import Literal
import uuid

import yaml


def dump_all(subjects_map, cca_local, lc):
    with open("migrate/subjects_map.json", "w") as file:
        json.dump(subjects_map, file, indent=2)
    with open("vocab/cca_local.yaml", "w") as file:
        yaml.dump(cca_local, file)
    with open("vocab/lc.yaml", "w") as file:
        yaml.dump(lc, file)


def main(file: str):
    with open(sys.argv[1], "r") as fp:
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
                # TODO use real identifiers, NS_URL chosen b/c there's no ideal option
                subject["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, term))
                subject["scheme"] = "cca_local"

            # Covers multiple LC authorities: LCNAF, LCSH, LCGFT
            elif auth.upper().startswith("LC"):
                if not row["Auth URI"]:
                    raise ValueError(
                        f"No Auth URI for LC subject: {term} ({auth})\nAll LC subjects must have an Auth URI."
                    )
                subject["id"] = row["Auth URI"]
                subject["scheme"] = "lc"

            subjects_map[row["VAULT value"]] = subject["id"]
            # combined terms are not added to the final vocab files (but are in the map)
            if status == "done":
                locals()[subject["scheme"]].append(subject)

        dump_all(subjects_map, cca_local, lc)


if __name__ == "__main__":
    main(sys.argv[1])
