import json
import mimetypes
import re
from urllib.parse import urlparse

from edtf import text_to_edtf


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


# ensure valid URLs
# prepend scheme to //www.youtube.com/... URLs seen in youtube attachments
# used in Record.related_identifiers
def get_url(url: str) -> str | None:
    parsed_url = urlparse(url)
    if parsed_url.scheme:
        return url
    elif parsed_url.netloc:
        return parsed_url._replace(scheme="https").geturl()
    return None


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


def visual_mime_type_sort(attachment) -> int:
    # Sort EQUELLA attachment dicts by MIME type, types previewable in Invenio
    # which is (according to readme): PDF, ZIP, CSV, MARKDOWN, XML, JSON, PNG, JPG, GIF
    # but also includes some audio and video types (don't know exactly which)
    # https://github.com/inveniosoftware/invenio-previewer
    # Order: TIFF > Non-HEIC/WBEP Images > PDF > Video > Markdown, CSV, XML > JSON > Audio > ZIP > others
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types#types
    # type=zip attachments have a "folder" but no "filename"
    fn = attachment.get("filename") or attachment["folder"]
    guess: str | None = mimetypes.guess_type(fn)[0]
    type, subtype = guess.split("/") if guess else ("unknown", "unknown")
    match type, subtype:
        case "image", "tiff":
            return 0
        case "image", _ if subtype not in ["heic", "webp"]:
            return 10
        case "application", "pdf":
            return 20
        case "video", _:
            return 25
        case "text", _ if subtype in ["csv", "markdown", "xml"]:
            return 30
        case "application", "json":
            return 40
        case "audio", _:
            return 45
        case "application", _ if subtype in ["zip", "x-zip-compressed"]:
            return 50
        case _, _:  # model, font types, subtypes not covered above
            return 60
