import yaml

# this is a deduped list of our values for mods/name/role/roleTerm
# with "editor" and "researcher" removed because they have exact matches in datacite
# but not the full list of MARC relator terms
# https://www.loc.gov/marc/relators/relaterm.html
roles = [
    # not in MARC relator terms
    # "academic partner",
    "architect",
    "artist",
    "associated name",
    "author",
    "author of introduction, etc.",
    "book designer",
    "bookjacket designer",
    "calligrapher",
    "cinematographer",
    # MARC says to use contributor
    # "collaborator",
    "compiler",
    "contributor",  # added due to above comment
    "creator",
    "curator",
    # not in MARC relator terms, use curator
    # "curator assistant",
    "designer",
    "founder",
    "illustrator",
    # next 3 all not in MARC relator terms
    # "installation artist",
    # "instructor assistant",
    # "instructor/curator",
    "interviewee",
    "interviewer",
    "manufacturer",
    "minute taker",
    "narrator",
    "organizer",
    # MARC says to use "organizer"
    # "organizer of meeting",
    # not in MARC relator terms...showing the bibliographic bias of MARC
    # "painter",
    # not in MARC relator terms, use performer or artist?
    # "performance artist",
    "performer",
    "photographer",
    "platemaker",
    # not in MARC relator terms, use author
    # "poet",
    "printer",
    "printmaker",
    "producer",
    # not in MARC relator terms, use teacher
    # "professor",
    "publisher",
    "recording engineer",
    "reviewer",
    "sculptor",
    # not in MARC relator terms, use artist rather than add singer
    # "singer songwriter",
    "speaker",
    "teacher",
    "transcriber",
    # not in MARC relator terms, various qualified "Writer of added text" terms are, use author
    # "writer",
]


def convert(role: str):
    return {
        "id": role.lower().replace(" ", ""),
        "title": {"en": role.capitalize()},
    }


if __name__ == "__main__":
    invenio_roles = [convert(role) for role in roles]
    filename = "vocab/roles.yaml"
    with open(filename, "w") as f:
        yaml.dump(invenio_roles, f, allow_unicode=True)
        print(f"Wrote Invenio roles fixture to {filename}")
