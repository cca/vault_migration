# see https://github.com/inveniosoftware/docs-invenio-rdm-restapi-example
# and https://inveniordm.docs.cern.ch/reference/rest_api_index/
import os
import sys
import urllib3

import requests

from record import Record
from utils import find_items

# shut up urllib3 SSL verification warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
token = os.environ.get("INVENIO_TOKEN") or os.environ.get("TOKEN")
if not token:
    raise Exception(
        "Error: provide a personal access token in the TOKEN or INVENIO_TOKEN env var"
    )


def post(r: Record):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    # create metadata-only draft
    draft_response = requests.post(
        "https://127.0.0.1:5000/api/records",  # TODO config for domain, port
        json=r.get(),
        verify=False,
        headers=headers,
    )
    print("HTTP {}".format(draft_response.status_code))
    if draft_response.status_code > 201:
        print(draft_response.text)
    draft_response.raise_for_status()
    draft_record = draft_response.json()
    print(draft_record["links"]["self"])
    # publish
    publish_response = requests.post(
        f"https://127.0.0.1:5000/api/records/{draft_record['id']}/draft/actions/publish",
        headers=headers,
        verify=False,
    )
    print("HTTP {}".format(publish_response.status_code))
    if publish_response.status_code > 201:
        print(publish_response.text)
    publish_response.raise_for_status()
    published_record = publish_response.json()
    print(published_record["links"]["self_html"])

    # you can use /api/records/<id>/communities
    # see https://github.com/inveniosoftware/invenio-rdm-records/blob/master/tests/resources/test_resources_communities.py#L32
    return published_record


if __name__ == "__main__":
    # support passing any number of single item json, search results json, or XML metadata files
    for file in sys.argv[1:]:
        items = find_items(file)
        for item in items:
            r = Record(item)
            post(r)
