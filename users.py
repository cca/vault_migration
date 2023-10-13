""" Convert EQUELLA taxonomy export into Invenio users fixture
https://inveniordm.docs.cern.ch/customize/vocabularies/users/
"""
import argparse
import json

import yaml


def convert(p):
    """convert EQUELLA personal names taxo term into Invenio name

    Args:
        term (dict): employee or student info dict from Workday

    Returns:
        dict|False: user info for Invenio or False if user should not be created
    """
    # using dict access & not .get() because we want KeyErrors to highlight problems
    # employees have work_email & students have inst_email, some temp workers have neither
    email = p.get("work_email") or p.get("inst_email")
    if not email or not email.endswith("@cca.edu"):
        return False
    return {
        "email": email,
        "username": p["username"],
        "full_name": f'{p["first_name"]} {p["last_name"]}',
        "affiliations": "California College of the Arts",
        "active": True,
        "confirmed": True,
        # TODO "roles" & "allow" arrays for permissions
    }


def main(args):
    people = []
    for file in args.files:
        with open(file, "r") as fh:
            data = json.load(fh)
            people += data["Report_Entry"]

    users = []
    for p in people:
        user = convert(p)
        if user:
            users.append(user)

    with open("vocab/users.yaml", "w") as f:
        yaml.dump(users, f, allow_unicode=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert our integrations JSON into Invenio users YAML"
    )
    parser.add_argument(
        "files",
        default=["data/employee_data.json"],
        help="Path to integrations JSON files (one or more)",
        nargs="*",
    )
    args = parser.parse_args()
    main(args)
