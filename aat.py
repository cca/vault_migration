""" Convert AAT JSON into Invenio subject vocab
https://inveniordm.docs.cern.ch/customize/vocabularies/subjects/
To get AAT JSON go to https://www.getty.edu/research/tools/vocabularies/aat/
view term and click the JSON link in the list of Semantic Views
We use <visual works by material or technique> in Libraries collection
https://www.getty.edu/vow/AATFullDisplay?find=&logic=AND&note=&subjectid=300191091
"""
import argparse
import json

import yaml


def main(args):
    with args.file:
        aat = json.load(args.file)

    vocab = []
    for term in aat["narrower"]:
        vocab.append(
            {"id": term["id"], "scheme": "AAT", "subject": term["_label"]["@value"]}
        )

    outfile = args.file.name.replace(".json", ".yaml")
    with open(outfile, "w") as fh:
        yaml.dump(vocab, fh, allow_unicode=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Convert the JSON representation of an AAT term into the Invenio subject YAML. This scripts takes only the "narrower" terms from the provided file.'
    )
    parser.add_argument(
        "file",
        help="Path to JSON AAT",
        nargs="?",
        type=argparse.FileType("r"),
    )
    args = parser.parse_args()
    main(args)
