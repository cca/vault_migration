"""Convert EQUELLA taxonomy export into Invenio users and names fixtures
https://inveniordm.docs.cern.ch/customize/vocabularies/users/
https://inveniordm.docs.cern.ch/customize/vocabularies/names/

Users are user accounts, names autocomplete when you fill in creator/contributor fields.
Script assumes data/employee_data.json & data/student_data.json but you can pass in
different paths to Workday JSON files.
"""

import argparse
import json
import re
from typing import Any

import yaml

ADMIN_ACCOUNTS: list[str] = ["ahaar", "ephetteplace", "mgoh"]
# See our `ACCOUNTS_USERNAME_REGEX` in invenio.cfg
# https://github.com/cca/cca_invenio/blob/main/invenio.cfg
USERNAME_REGEX: re.Pattern = re.compile(r"[a-z][a-z0-9_\.-]{0,23}")


def convert_to_vocabs(
    people: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """convert Workday JSON into Invenio users

    Args:
        term (dict): employee or student info dict from Workday

    Returns:
        dict|False: user info for Invenio or False if user should not be created
    """
    names: list[dict[str, Any]] = []
    usernames: set[str] = set()
    users: list[dict[str, Any]] = []
    for p in people:
        # alum workers with have entries in both files, so we need to skip them
        if p["username"] in usernames:
            continue

        # employees have work_email & students have inst_email, some temp workers have neither
        email: str | None = p.get("work_email") or p.get("inst_email")
        if not email or not email.endswith("@cca.edu"):
            continue

        if not USERNAME_REGEX.match(p["username"]):
            print(f"Invalid username: {p['username']}")
            continue

        # We have a valid user!
        url_id = f"https://portal.cca.edu/people/{p['username']}/"
        names.append(
            {
                "family_name": p["last_name"],
                "given_name": p["first_name"],
                "id": url_id,
                # Requires "emai" & "url" scheme in RDM_RECORDS_PERSONORG_SCHEMES and
                # VOCABULARIES_NAMES_SCHEMES in invenio.cfg
                "identifiers": [
                    {
                        "identifier": url_id,
                        "scheme": "url",
                    },
                    {
                        "identifier": email,
                        "scheme": "email",
                    },
                ],
                "affiliations": [{"id": "01mmcf932"}],  # ROR ID for CCA
            }
        )
        usernames.add(p["username"])
        user: dict[str, Any] = {
            "email": email,
            "username": p["username"],
            "full_name": f"{p['first_name']} {p['last_name']}",
            "affiliations": "California College of the Arts",
            "active": True,
            "confirmed": True,
        }
        if p["username"] in ADMIN_ACCOUNTS:
            user["roles"] = ["admin"]
        users.append(user)

    return names, users


def main(args):
    people: list[dict[str, Any]] = []
    for file in args.files:
        with open(file, "r") as fh:
            data = json.load(fh)
            people += data["Report_Entry"]

    names, users = convert_to_vocabs(people)

    with open("vocab/test_users.yaml", "r") as f:
        # add static accounts (e.g. library-test-student-1)
        accounts: list[dict[str, Any]] = yaml.load(f, Loader=yaml.FullLoader)
        users.extend(accounts)

    with open("vocab/names.yaml", "w") as f:
        yaml.dump(names, f, allow_unicode=True)

    with open("vocab/users.yaml", "w") as f:
        yaml.dump(users, f, allow_unicode=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert our integrations JSON into Invenio users YAML"
    )
    parser.add_argument(
        "files",
        default=["data/employee_data.json", "data/student_data.json"],
        help="Path to integrations JSON files (one or more)",
        nargs="*",
    )
    args = parser.parse_args()
    main(args)
