# This script takes a CSV export of our VAULT Subjects & Genres sheet
# https://docs.google.com/spreadsheets/d/1la_wsFPOkHLjpv4-f3tWwMsCd0_xzuqZ5xp_p1zAAoA/edit#gid=1465207925
# and converts it into three files:
# - subjects_map.json: a mapping of VAULT subject strings to Invenio subject IDs
# - cca_local.yaml: a YAML file of CCA Local subjects
# - lc.yaml: a YAML file of Library of Congress subjects (from multiple authorities)
# TODO should this be name, subject, place, etc. type themed vocabs instead of by authority?
#
# Usage:
# python migrate/mk_subjects.py subjects.csv
# It is meant to be run from the project root like this. It takes additional static vocabularies we made
# in the "vocabs" dir and includes them in the cca_local subject. The 2 YAML files are written to the
# vocab directory and the JSON file is written to the migrate directory.
import csv
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml


def get_uuid(term: str) -> str:
    # This doesn't make sense but is consistent across runs so it'll do
    return str(uuid.uuid5(uuid.NAMESPACE_URL, term))


def dump_all(subjects_map, vocabs: dict[str, Any]) -> None:
    with open("migrate/subjects_map.json", "w") as file:
        json.dump(subjects_map, file, indent=2)
    for name, data in vocabs.items():
        with open(f"vocab/{name}.yaml", "w") as file:
            yaml.dump(data, file)
    # if we have INVENIO_REPO, copy output files to the repo's vocab dir
    if "INVENIO_REPO" in os.environ:
        dest: Path = Path(os.environ["INVENIO_REPO"]) / "app_data" / "vocabularies"
        if dest.exists():
            for name, data in vocabs.items():
                with open(dest / f"{name}.yaml", "w") as file:
                    yaml.dump(data, file)


def main(file: str) -> None:
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

            # ULAN or Wikidata subjects are added to cca_local but with their Auth URI as the ID
            if auth.upper() in ("ULAN", "WIKIDATA"):
                if not row["Auth URI"]:
                    raise ValueError(
                        f"No Auth URI for ULAN/Wikidata term: {term}\nExternal terms must have an Auth URI."
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
        for filename in ["subject_names.yaml"]:
            with open(Path("vocab") / filename, "r") as fh:
                terms: list[dict[str, str]] = yaml.load(fh, Loader=yaml.FullLoader)
                for t in terms:
                    # if term has already been added to the subjects_map, skip it
                    if (term_text := t["subject"].lower()) in subjects_map:
                        continue
                    # assign an ID that matches what we have in the map from combined subjects.csv terms
                    t["id"] = get_uuid(t["subject"])
                    subjects_map[term_text] = t["id"]
                    locals()[t["scheme"]].append(t)

        dump_all(subjects_map, {"cca_local": cca_local, "lc": lc})


if __name__ == "__main__":
    main(sys.argv[1])
