# see https://github.com/inveniosoftware/docs-invenio-rdm-restapi-example
# and https://inveniordm.docs.cern.ch/reference/rest_api_index/
import os
import sys
from typing import Any, Literal

import urllib3
from dotenv import load_dotenv
from record import Record
from requests import Response, request
from utils import find_items

load_dotenv()
# shut up urllib3 SSL verification warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
token: str | None = os.environ.get("INVENIO_TOKEN") or os.environ.get("TOKEN")
verify: bool = bool(os.environ.get("HTTPS_VERIFY", False))
if not token:
    raise Exception(
        "Error: provide a personal access token in the TOKEN or INVENIO_TOKEN env var"
    )
headers: dict[str, str] = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}",
}


def http(
    method: Literal["get", "post", "post"],
    url: str,
    json: Any = None,
    headers: dict[str, str] = headers,
    verify: bool = verify,
) -> Response:
    """Helper method around requests with our headers & prints response status"""
    response: Response = request(
        method=method, url=url, headers=headers, json=json, verify=verify
    )
    print(f"HTTP {response.status_code} {url}")
    return response


def post(r: Record) -> dict[str, Any]:
    # create metadata-only draft
    draft_resp: Response = http(
        "post",
        f"https://{os.environ['HOST']}/api/records",
        json=r.get(),
    )

    if draft_resp.status_code > 201:
        print(draft_resp.text)
    draft_resp.raise_for_status()
    draft_record: dict[str, Any] = draft_resp.json()
    print("Draft:", draft_record["links"]["self"])

    # publish
    publish_resp: Response = http(
        "post",
        f"https://{os.environ['HOST']}/api/records/{draft_record['id']}/draft/actions/publish",
    )

    # if publish_response.status_code > 201: print(publish_response.text)
    publish_resp.raise_for_status()
    published_record: dict[str, Any] = publish_resp.json()
    print("Published:", published_record["links"]["self_html"])

    # add to communities
    comms_to_add: set[str] = set()
    for slug in r.communities:
        # check that each community exists first
        get_comm_resp: Response = http(
            "get",
            f"https://{os.environ['HOST']}/api/communities/{slug}",
        )

        if get_comm_resp.status_code == 404:
            print(f"Community {slug} does not exist")
        elif get_comm_resp.status_code == 200:
            community = get_comm_resp.json()
            # cannot add a public record to a restricted community
            if (
                published_record["access"]["record"] == "public"
                and community["access"]["visibility"] == "restricted"
            ):
                print(
                    f"ERROR: cannot add public record {published_record['links']['self_html']} to restricted community {community['links']['self_html']}"
                )
                continue
            comms_to_add.add(slug)

        if len(comms_to_add):
            communities: dict[str, list[dict[str, str]]] = {
                "communities": [{"id": slug} for slug in comms_to_add]
            }
            add_to_comm_resp: Response = http(
                "post",
                published_record["links"]["communities"],
                json=communities,
            )

            if add_to_comm_resp.status_code > 201:
                print(
                    f"Error adding {published_record['links']['self_html']} to communities: {comms_to_add}"
                )
                print(add_to_comm_resp.text)

            community_requests = add_to_comm_resp.json()
            for community_request in community_requests["processed"]:
                comm_req_accept_resp: Response = http(
                    "post",
                    community_request["request"]["links"]["actions"]["accept"],
                    # opportunity to provide comment on acceptance
                    # https://inveniordm.docs.cern.ch/reference/rest_api_requests/#comment-payload
                    json={},
                )
                if comm_req_accept_resp.status_code > 202:
                    print(
                        f"Error accepting community request for {published_record['links']['self_html']} to community {community_request['request']['community']['links']['self_html']}"
                    )
                    print(comm_req_accept_resp.text)

    return published_record


if __name__ == "__main__":
    # support passing any number of single item json, search results json, or XML metadata files
    for file in sys.argv[1:]:
        items: list = find_items(file)
        for item in items:
            r: Record = Record(item)
            r.attachments = []  # ! use import.py to add files
            post(r)
