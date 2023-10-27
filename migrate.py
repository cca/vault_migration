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
    # ? should we raise a TypeError here?


def postprocessor(path, key, value):
    """XML postprocessor, ensure that empty XML nodes like <foo></foo> are empty
    dicts, not None, so we can continue chaining .get() calls on the result."""
    if value is None:
        return (key, {})
    return (key, value)


class Record:
    def __init__(self, item):
        self.xml = xmltodict.parse(item["metadata"], postprocessor=postprocessor)["xml"]
        self.title = item.get("name", "Untitled")

    @property
    def abstracts(self):
        abs = self.xml.get("mods", {}).get("abstract", "")
        return mklist(abs)

    @property
    def descriptions(self):
        # extra /mods/abstract entries, mods/noteWrapper/note
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-descriptions-0-n
        # https://127.0.0.1:5000/api/vocabularies/descriptiontypes
        # types: abstract, methods, series-information, table-of-contents, technical-info, other

        # we ensure there's at least one abstract (see def abstracts)
        desc = [{"type": "abstract", "description": a} for a in self.abstracts[1:]]

        # MODS note types: https://www.loc.gov/standards/mods/mods-notes.html
        # Mudflats has only handwritten & identification notes
        # All our note values: acquisition, action, additional artists, additional performers, additional physical form, depicted persons, exhibitions, funding, handwritten, identification, local, medium, original location, publications, source identifier, venue, version, version identification
        notes = mklist(self.xml.get("mods", {}).get("noteWrapper", {}).get("note"))
        for note in notes:
            if type(note) == str:
                desc.append({"type": "other", "description": note})
            elif type(note) == dict:
                desc.append({"type": "other", "description": note.get("#text")})

        return desc

    @property
    def addl_titles(self):
        # extra /mods/titleInfo/title entries, titleInfo/subtitle
        # https://inveniordm.docs.cern.ch/reference/metadata/#additional-titles-0-n
        # Types: https://127.0.0.1:5000/api/vocabularies/titletypes
        # alternative-title, other, subtitle, translated-title
        atitles = []
        titleinfos = mklist(self.xml.get("mods", {}).get("titleInfo"))
        for idx, titleinfo in enumerate(titleinfos):
            # all subtitles
            for subtitle in mklist(titleinfo.get("subTitle")):
                atitles.append({"title": subtitle, "type": {"id": "subtitle"}})
            # titles other than the first
            for title in mklist(titleinfo.get("title")):
                if idx > 0:
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

    @property
    def type(self):
        # https://127.0.0.1:5000/api/vocabularies/resourcetypes
        # our subset of the full list of resource types:
        # bachelors-thesis, publication, event, image, publication-article,
        # masters-thesis, other, thesis, video
        pass

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
                "additional_descriptions": self.descriptions,
                "additional_titles": self.addl_titles,
                # mods/name/namePart, non-creator contributors
                # contributor/creator roles: contactperson, datacollector, datacurator, datamanager, distributor, editor, hostinginstitution, other, producer, projectleader, projectmanager, projectmember, registrationagency, registrationauthority, relatedperson, researchgroup, researcher, rightsholder, sponsor, supervisor, workpackageleader
                "contributors": [],
                # https://inveniordm.docs.cern.ch/reference/metadata/#creators-1-n
                "creators": [],
                # additional NON-PUBLICATION dates
                # date types: accepted, available, collected, copyrighted, created, issued, other, submitted, updated, valid, withdrawn
                "dates": [],
                "description": self.abstracts[0],
                "formats": [],
                "locations": [],
                # date created, add other/additional dates to dates[]
                # https://inveniordm.docs.cern.ch/reference/metadata/#publication-date-1
                "publication_date": "",
                "publisher": "",
                # relation types: cites, compiles, continues, describes, documents, haspart, hasversion, iscitedby, iscompiledby, iscontinuedby, isderivedfrom, isdescribedby, isdocumentedby, isidenticalto, isnewversionof, isobsoletedby, isoriginalformof, ispartof, ispreviousversionof, isreferencedby, isrequiredby, isreviewedby, issourceof, issupplementto, issupplementedby
                "related_identifiers": [],
                # options defined in resource_types.yaml fixture
                # https://inveniordm.docs.cern.ch/reference/metadata/#resource-type-1
                "resource_type": {},
                # mods/accessCondition with license URL in href attribute
                # https://127.0.0.1:5000/api/vocabularies/licenses
                # https://inveniordm.docs.cern.ch/reference/metadata/#rights-licenses-0-n
                # options defined in licenses.csv fixture
                "rights": [],
                "sizes": [],
                "subjects": [],
                "title": self.title,
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
        if f.name.endswith(".xml"):
            xml = f.read()
            item = {"metadata": xml}
        else:
            item = json.load(f)
        record = Record(item)
    # JSON pretty print record
    json.dump(record.get(), sys.stdout, indent=2)
