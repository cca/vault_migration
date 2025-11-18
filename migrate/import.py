# see https://github.com/inveniosoftware/docs-invenio-rdm-restapi-example
# and https://inveniordm.docs.cern.ch/reference/rest_api_index/
import json
import os
from pathlib import Path
from typing import Any

import click
import requests
import urllib3
from dotenv import load_dotenv
from record import Record

load_dotenv()
# shut up urllib3 SSL verification warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
token: str | None = os.environ.get("INVENIO_TOKEN") or os.environ.get("TOKEN")
if not token:
    raise Exception(
        "Error: provide a personal access token in the TOKEN or INVENIO_TOKEN env var"
    )
domain: str = f"https://{os.environ['HOST']}"
verify: bool = os.environ.get("HTTPS_VERIFY", "").lower() == "true"
headers: dict[str, str] = {
    "Accept": "application/json",
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}


def verbose_print(*args) -> None:
    if verbose:
        click.echo(*args)


def get_item(json_path: Path) -> dict:
    with open(json_path, "r") as f:
        return json.load(f)


def read_map(map_file: str) -> dict[str, Any]:
    if os.path.exists(map_file):
        with open(map_file, "r") as f:
            return json.load(f)
    else:
        verbose_print(f"No mapping file found at {map_file}, creating an empty one")
        return {}


def update_map(
    map: dict[str, Any], vault: dict[str, Any], record: Record, invenio_id: str
) -> dict[str, Any]:
    url = vault["links"]["view"]
    if url in map:
        verbose_print(f"Warning: VAULT item {url} already in mapping, overwriting")
    map[url] = {
        "id": invenio_id,
        "title": record.title,
        "owner": vault.get("owner", {}).get("id"),
        "collaborators": [c.get("id") for c in vault.get("collaborators", [])],
        "viewlevel": record.viewlevel,
        "status": "imported",
    }
    return map


def write_map(map_file: str, id_map: dict[str, Any]) -> None:
    with open(map_file, "w") as f:
        json.dump(id_map, f, indent=2)
        click.echo(f"Wrote ID mapping to {map_file}")


def create_draft(record: dict[str, Any]) -> dict[str, Any]:
    draft_response: requests.Response = requests.post(
        f"{domain}/api/records",
        json=record,
        verify=verify,
        headers=headers,
    )
    verbose_print(f"HTTP {draft_response.status_code} {draft_response.url}")
    if draft_response.status_code > 201:
        click.echo(draft_response.text, err=True)
    if errors:
        draft_response.raise_for_status()
    return draft_response.json()


def add_files(directory: Path, record: Record, draft: dict[str, Any]):
    # add files to draft record
    # four steps: initiate, upload (all), commit (all), set default preview
    # ! Unable to set order as API docs suggest, files.order is dropped
    # ! https://github.com/inveniosoftware/invenio-app-rdm/issues/2573
    keys: list[dict[str, str]] = [{"key": att["name"]} for att in record.attachments]
    files_response: requests.Response = requests.post(
        draft["links"]["files"],
        json=keys,
        headers=headers,
        verify=verify,
    )
    verbose_print(f"HTTP {files_response.status_code} {files_response.url}")
    if errors:
        files_response.raise_for_status()
    files_area = files_response.json()

    # upload one by one
    # TODO use httpx to do in parallel?
    for attachment in record.attachments:
        binary_headers: dict[str, str] = headers.copy()
        binary_headers["Content-Type"] = "application/octet-stream"
        with open(directory / attachment["name"], "rb") as f:
            upload_response: requests.Response = requests.put(
                # ? Would it be better to use files_area['links']['self'] for some reason?
                f"{domain}/api/records/{draft['id']}/draft/files/{attachment['name']}/content",
                data=f,
                headers=binary_headers,
                verify=verify,
            )
            verbose_print(f"HTTP {upload_response.status_code} {upload_response.url}")
            if errors:
                upload_response.raise_for_status()

    # commit one by one
    # ? Should we do this above in the same loop?
    # TODO httpx parallel
    for commit_link in [entry["links"]["commit"] for entry in files_area["entries"]]:
        commit_response: requests.Response = requests.post(
            commit_link,
            headers=headers,
            verify=verify,
        )
        verbose_print(f"HTTP {commit_response.status_code} {commit_response.url}")
        if errors:
            commit_response.raise_for_status()

    # set default preview which was in our original record
    preview_response: requests.Response = requests.put(
        draft["links"]["self"],
        json=record.get(),
        headers=headers,
        verify=verify,
    )
    verbose_print(f"HTTP {preview_response.status_code} {preview_response.url}")
    if errors:
        preview_response.raise_for_status()


def publish(draft: dict[str, Any]) -> dict[str, Any]:
    publish_response: requests.Response = requests.post(
        f"{domain}/api/records/{draft['id']}/draft/actions/publish",
        headers=headers,
        verify=verify,
    )
    verbose_print(f"HTTP {publish_response.status_code} {publish_response.url}")
    # draft created is a 200 Created response, but published is 202 Accepted
    if publish_response.status_code > 202:
        click.echo(publish_response.text, err=True)
    if errors:
        publish_response.raise_for_status()
    return publish_response.json()


def add_to_communities(published_record: dict[str, Any], communities: set[str]) -> None:
    # add to communities
    comms_to_add: set[str] = set()
    for slug in communities:
        # check that each community exists first
        get_comm_resp: requests.Response = requests.get(
            f"https://{os.environ['HOST']}/api/communities/{slug}",
            headers=headers,
            verify=verify,
        )
        verbose_print(f"HTTP {get_comm_resp.status_code} {get_comm_resp.url}")

        if get_comm_resp.status_code == 404:
            click.echo(f"Community {slug} does not exist")
        elif get_comm_resp.status_code == 200:
            community = get_comm_resp.json()
            # cannot add a public record to a restricted community
            if (
                published_record["access"]["record"] == "public"
                and community["access"]["visibility"] == "restricted"
            ):
                click.echo(
                    f"ERROR: cannot add public record {published_record['links']['self_html']} to restricted community {community['links']['self_html']}",
                    err=True,
                )
                continue
            comms_to_add.add(slug)

        if len(comms_to_add):
            comms_data: dict[str, list[dict[str, str]]] = {
                "communities": [{"id": slug} for slug in comms_to_add]
            }
            add_to_comm_resp: requests.Response = requests.post(
                published_record["links"]["communities"],
                json=comms_data,
                headers=headers,
                verify=verify,
            )
            verbose_print(f"HTTP {add_to_comm_resp.status_code} {add_to_comm_resp.url}")
            if errors:
                add_to_comm_resp.raise_for_status()

            # above only opened a request, now we accept the requests in each community
            community_requests = add_to_comm_resp.json()
            for community_request in community_requests["processed"]:
                if (
                    community_request["request"]["is_open"]
                    and not community_request["request"]["is_closed"]
                    and community_request["request"]["links"]["actions"].get("accept")
                ):
                    comm_req_accept_resp: requests.Response = requests.post(
                        community_request["request"]["links"]["actions"]["accept"],
                        # opportunity to provide comment on acceptance
                        # https://inveniordm.docs.cern.ch/reference/rest_api_requests/#comment-payload
                        json={},
                        headers=headers,
                        verify=verify,
                    )
                    verbose_print(
                        f"HTTP {comm_req_accept_resp.status_code} {comm_req_accept_resp.url}"
                    )
                    if errors:
                        comm_req_accept_resp.raise_for_status()
                else:
                    verbose_print(
                        f"No need to accept community request for {published_record['links']['self_html']} to community {community_request['community_id']}. The request is either closed or was automatically accepted."
                    )

            click.echo(
                f"Added {published_record['links']['self_html']} to communities: {comms_to_add}"
            )


@click.command(
    help="Import items and their attachments into InvenioRDM. This expects a directory formatted like the equella_scripts/collection-export tool with attachments inside and a metadata subdirectory with an item.json file."
)
@click.help_option("-h", "--help")
@click.argument("directory", type=click.Path(exists=True), required=True)
@click.option("--ignore-errors", "-i", help="Ignore errors and continue", is_flag=True)
@click.option("--no-map", help="Do not update the ID mapping file", is_flag=True)
@click.option(
    "--map-file",
    default="id-map.json",
    help="Path to ID mapping file (default: id-map.json)",
)
@click.option("--verbose", "-v", "is_verbose", help="Print more output", is_flag=True)
def main(
    directory: str, is_verbose: bool, ignore_errors: bool, no_map: bool, map_file: str
) -> None:
    # cannot annotate these global vars
    global errors, verbose
    errors = not ignore_errors
    verbose = is_verbose

    item: dict[str, Any] = get_item(Path(directory) / "metadata" / "item.json")
    id_map: dict[str, Any] = read_map(map_file) if not no_map else {}
    record: Record = Record(item)

    click.echo(f"Importing {record.title} from {directory}")
    draft: dict[str, Any] = create_draft(record.get())

    if len(record.attachments):
        add_files(Path(directory), record, draft)

    published_record: dict[str, Any] = publish(draft)

    add_to_communities(published_record, record.communities)

    click.echo(f"Published: {published_record['links']['self_html']}")

    # ? should we update the map after publication or after communities?
    if not no_map:
        id_map = update_map(id_map, item, record, published_record["id"])
        write_map(map_file, id_map)


if __name__ == "__main__":
    main()
