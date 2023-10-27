"""
Convert an EQUELLA item into an Invenio record.

Eventually this will accept a _directory_ containing the item's JSON and its
attachments, but for staters we are taking just JSON.
"""
import json
import sys

import xmltodict


def mklist(x):
    # ensure value is a list
    if type(x) == list:
        return x
    elif type(x) == str or type(x) == dict:
        return [x]
    elif x is None:
        return []


class Record:
    def __init__(self, item):
        self.xml = xmltodict.parse(item["metadata"])["xml"]

    @property
    def abstracts(self):
        abs = self.xml.get("mods", {}).get("abstract", None)
        return mklist(abs)

    @property
    def addl_titles(self):
        # extra /mods/titleInfo/title entries, titleInfo/subtitle
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-titles-0-n
        # Types: https://127.0.0.1:5000/api/vocabularies/titletypes
        # alternative-title, other, subtitle, translated-title
        atitles = []
        titleinfos = mklist(self.xml.get("mods", {}).get("titleInfo"))
        for ti_idx, titleinfo in enumerate(titleinfos):
            # all subtitles
            for subtitle in mklist(titleinfo.get("subTitle")):
                atitles.append({"title": subtitle, "type": {"id": "subtitle"}})
            # other titles other than the first
            for t_idx, title in enumerate(mklist(titleinfo.get("title"))):
                if ti_idx > 0 and t_idx > 0:
                    atype = titleinfo.get("@type")
                    if atype == "alternative":
                        atitles.append(
                            {"title": title, "type": {"id": "alternative-title"}}
                        )
                    elif atype == "translated":
                        atitles.append(
                            {"title": title, "type": {"id": "translated-title"}}
                        )
                    else:
                        atitles.append({"title": title, "type": {"id": "other"}})
        return atitles

    def get(self):
        return {
            # TODO restricted access based on local/viewLevel value
            "access": {
                "files": "public",
                "record": "public",
            },
            # ! blocked until we know what custom fields we'll have
            "custom_fields": {},
            # TODO add files, figure out best one to show first (prefer image formats?)
            "files": {
                "enabled": False,
                "order": [],
            },
            "metadata": {
                # mods/abtract after the 1st (self.abstracts[1:]), notes
                # addl desc can have a type (abstract is one of types) but root desc cannot
                # https://inveniordm.docs.cern.ch/reference/metadata/#additional-descriptions-0-n
                # https://127.0.0.1:5000/api/vocabularies/descriptiontypes
                "additional_descriptions": [],
                "additional_titles": self.addl_titles,
                # mods/name/namePart, non-creator contributors
                "contributors": [],
                # https://inveniordm.docs.cern.ch/reference/metadata/#creators-1-n
                "creators": [],
                # additional NON-PUBLICATION dates
                "dates": [],
                # mods/abstract?
                "description": self.abstracts[0],
                # date created, add other/additional dates to dates[]
                # https://inveniordm.docs.cern.ch/reference/metadata/#publication-date-1
                "publication_date": "",
                # options defined in resource_types.yaml fixture
                # https://inveniordm.docs.cern.ch/reference/metadata/#resource-type-1
                "resource_type": {},
                # mods/accessCondition with license URL in href attribute
                # https://127.0.0.1:5000/api/vocabularies/licenses
                # https://inveniordm.docs.cern.ch/reference/metadata/#rights-licenses-0-n
                # options defined in licenses.csv fixture
                "rights": [],
                "subjects": [],
                "title": item["name"],
            },
            # https://inveniordm.docs.cern.ch/reference/metadata/#parent
            # ? Does adding a parent community while creating the draft work or do
            # ? we have to use additional API calls afterwards?
            # ? Can we specifiy parent.access.owned_by here to set the owner?
            # collection, mods/relatedItem?
            "parent": {"communities": {}},
        }


if __name__ == "__main__":
    # we assume first arg is path to the item JSON
    with open(sys.argv[1]) as f:
        item = json.load(f)
        record = Record(item)
    # JSON pretty print record
    json.dump(record.get(), sys.stdout, indent=2)
