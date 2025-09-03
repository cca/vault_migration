"""Create a CSV of names in our EQUELLA "LIBRARIES - subject name" taxonomy
that need to be looked up in an external authority (OCLC, ULAN) to get URIs"""

import csv
import json

import click


@click.command()
@click.help_option("--help", "-h")
@click.argument(
    "file",
    type=click.File("r"),
    required=True,
)
def main(file) -> None:
    """Write external authority names in FILE ("LIBRARIES - subject name" taxo JSON) to taxos/names.csv to be added to subjects spreadsheet"""
    with file:
        terms: list[dict[str, str]] = json.load(file)

    with open("taxos/names.csv", "w") as f:
        writer = csv.writer(f)
        for term in terms:
            if not term["fullTerm"].startswith("local"):
                writer.writerow(
                    ["Name", term["term"], term["fullTerm"].split("\\")[0].upper()]
                )


if __name__ == "__main__":
    main()
