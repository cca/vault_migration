import json
import re

from edtf import text_to_edtf


def mklist(x) -> list:
    # ensure value is a list
    if type(x) == list:
        return x
    elif type(x) == str or type(x) == dict:
        return [x]
    elif x is None:
        return []
    else:
        raise TypeError(f"mklist: invalid type: {type(x)}")


# support three types of files: single item json, search results json with
# multiple items in "results" property, and XML metadata with no item JSON
def find_items(file) -> list:
    if file.endswith(".json"):
        with open(file) as f:
            data = json.load(f)
            if data.get("results"):
                return data["results"]
            else:
                return [data]
    elif file.endswith(".xml"):
        with open(file) as f:
            xml = f.read()
            return [{"metadata": xml}]
    # non-data file (like .py or .txt) so skip gracefully
    return []


# EDTF seasons conversion
# https://www.loc.gov/standards/datetime/
# "The values 21, 22, 23, 24 may be used used to signify ' Spring', 'Summer', 'Autumn', 'Winter', respectively, in place of a month value (01 through 12) for a year-and-month format string."
def to_edtf(s) -> str | None:
    # map season to approx month in season
    season_map = {
        "21": "02",
        "22": "05",
        "23": "08",
        "24": "11",
    }
    text = text_to_edtf(s)
    if text:
        season_match = re.match(r"\d{4}-(2\d)", text)
        season = season_match.group(1) if season_match else False
        if season:
            # if we somehow get a season out of range, we want this to throw a KeyError
            return f"{text[:4]}-{season_map[season]}"
    return text
