import os
import sys
import urllib3

import requests

from record import Record
from utils import find_items

# shut up urllib3 SSL verification warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
token = os.environ.get("TOKEN", False) or os.environ.get("INVENIO_TOKEN", False)
if not token:
    raise Exception(
        "Error: provide a personal access token in the TOKEN or INVENIO_TOKEN env var"
    )


def post(r: Record):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer {}".format(token),
    }
    # create metadata-only draft
    response = requests.post(
        "https://127.0.0.1:5000/api/records",
        json=r.get(),
        verify=False,
        headers=headers,
    )
    print("HTTP {}".format(response.status_code))
    response.raise_for_status()
    record = response.json()
    print(record["links"]["self"])
    return record


if __name__ == "__main__":
    # support passing any number of single item json, search results json, or XML metadata files
    for file in sys.argv[1:]:
        items = find_items(file)
        for item in items:
            r = Record(item)
            post(r)
