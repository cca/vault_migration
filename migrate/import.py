# see https://github.com/inveniosoftware/docs-invenio-rdm-restapi-example
# and https://inveniordm.docs.cern.ch/reference/rest_api_index/
import json
import os
from pathlib import Path
import urllib3

import click
from dotenv import load_dotenv
import requests

from record import Record

# shut up urllib3 SSL verification warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
token: str | None = os.environ.get("INVENIO_TOKEN") or os.environ.get("TOKEN")
if not token:
    raise Exception(
        "Error: provide a personal access token in the TOKEN or INVENIO_TOKEN env var"
    )

# load config from .env
load_dotenv()
port: str | None = os.environ.get("PORT")
domain: str = f"https://{os.environ['HOST']}{f':{port}' if port else ''}"
verify: bool = os.environ.get("HTTPS_VERIFY", "").lower() == "true"


def verbose_print(*args) -> None:
    if verbose:
        click.echo(*args)


def get_item(itemjson: Path) -> dict:
    with open(itemjson, "r") as f:
        return json.load(f)


def create_draft(record: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    draft_response = requests.post(
        f"{domain}/api/records",
        json=record,
        verify=verify,
        headers=headers,
    )
    verbose_print(f"HTTP {draft_response.status_code}")
    if draft_response.status_code > 201:
        click.echo(draft_response.text, err=True)
    draft_response.raise_for_status()
    draft_record = draft_response.json()
    return draft_record


def publish(draft: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    publish_response = requests.post(
        f"{domain}/api/records/{draft['id']}/draft/actions/publish",
        headers=headers,
        verify=verify,
    )
    verbose_print(f"HTTP {publish_response.status_code}")
    if publish_response.status_code > 201:
        click.echo(publish_response.text, err=True)
    publish_response.raise_for_status()
    published_record = publish_response.json()

    # you can use /api/records/<id>/communities
    # see https://github.com/inveniosoftware/invenio-rdm-records/blob/master/tests/resources/test_resources_communities.py#L32
    return published_record


@click.command(
    help="Import items and their attachments into InvenioRDM. This expects a directory formatted like the equella_scripts/collection-export tool with attachments inside and a metadata subdirectory with an item.json file."
)
@click.help_option("-h", "--help")
@click.argument("dir", type=click.Path(exists=True), required=True)
# @click.option("--ignore-errors", "-i", help="Ignore errors and continue", is_flag=True)
@click.option("--verbose", "-v", "is_verbose", help="Print more output", is_flag=True)
def main(dir: str, is_verbose: bool):
    global verbose
    verbose = is_verbose
    item = get_item(Path(dir) / "metadata" / "item.json")
    record = Record(item)
    click.echo(f"Importing {record.title} from {dir}...")
    draft = create_draft(record.get())
    # TODO add files
    published_record = publish(draft)
    # TODO add to community
    click.echo(f"Published: {published_record['links']['self_html']}")


if __name__ == "__main__":
    main()
