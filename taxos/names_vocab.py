"""Convert "LIBRARIES - subject name" EQUELLA taxonomy to Invenio subjects
vocabulary which we will save to vocab/names.yaml & append to
vocab/cca_local.yaml with migrate/mk_subjects.py"""

import json

import click
import yaml


def convert(term: dict[str, str]) -> dict[str, str] | None:
    """convert EQUELLA local auth names taxo term into Invenio name
    we will manually look up URIs for OCLC & ULAN auth names in subjects spreadsheet

    Args:
        term (dict): { "term": "Wang, Wayne, 1949-", "fullTerm": "oclc\\personal\\Wang, Wayne, 1949-", }

    Returns:
        dict: { "subject": "Wang, Wayne, 1949-", "scheme": "cca_local" }
    """
    if term["fullTerm"].startswith("local"):
        return {"subject": term["term"], "scheme": "cca_local"}
    return None


@click.command()
@click.help_option("--help", "-h")
@click.argument(
    "file",
    type=click.File("r"),
    required=True,
)
def main(file) -> None:
    """Convert FILE ("LIBRARIES - subject name" taxo JSON) to Invenio subjects names.yaml"""
    output: list[dict[str, str]] = []
    with file:
        terms: list[dict[str, str]] = json.load(file)

    for name in terms:
        if converted := convert(name):
            output.append(converted)

    with open("vocab/subject_names.yaml", "w") as f:
        yaml.dump(output, f, allow_unicode=True)


if __name__ == "__main__":
    main()
