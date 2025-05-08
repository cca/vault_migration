# Create an example record with a cca:course custom field
# Script substantially based on api.py
from datetime import date
import os
from typing import Any
import urllib3

import requests

# shut up urllib3 SSL verification warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
token: str | None = os.environ.get("INVENIO_TOKEN") or os.environ.get("TOKEN")
verify: bool = bool(os.environ.get("HTTPS_VERIFY", False))
if not token:
    raise Exception(
        "Error: provide a personal access token in the TOKEN or INVENIO_TOKEN env var"
    )


def post() -> dict[str, Any]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    metadata: dict[str, Any] = {
        "access": {"files": "public", "record": "public"},
        "custom_fields": {
            "cca:course": {
                "colocated_sections": ["COURSE_SECTION-3-42783"],
                "department": "Graduate Architecture",
                "department_code": "MARCH",
                "section": "MARCH-6040-1",
                "section_calc_id": "MARCH-6040-1_AP_Summer_2025",
                "section_refid": "COURSE_SECTION-3-42782",
                "term": "Summer 2025",
                "title": "Urban Fictions: Dwelling in Between",
                "instructors": [
                    {
                        "employee_id": "5XXXXX",
                        "uid": "100XXXXX",
                        "first_name": "Frida",
                        "middle_name": "",
                        "last_name": "Kahlo",
                        "username": "fkahlo",
                    }
                ],
                "instructors_string": "Frida Kahlo",
            }
        },
        "files": {
            "enabled": False,
        },
        "metadata": {
            "additional_descriptions": [],
            "additional_titles": [],
            "contributors": [],
            "creators": [
                {
                    "person_or_org": {
                        "given_name": "Test",
                        "family_name": "Student",
                        "type": "personal",
                    },
                    "role": {"id": "creator"},
                    "affiliations": [{"id": "01mmcf932"}],
                },
            ],
            "dates": [],
            "description": "Example course work item.",
            "formats": [],
            "locations": {"features": []},
            "publication_date": date.today().isoformat(),
            "publisher": "",
            "related_identifiers": [],
            "resource_type": {"id": "publication"},
            "rights": [{"id": "copyright"}],
            "sizes": [],
            "subjects": [],
            "title": "Example Course Work",
        },
    }
    # create metadata-only draft
    draft_response: requests.Response = requests.post(
        "https://127.0.0.1:5000/api/records",  # TODO config for domain, port
        headers=headers,
        json=metadata,
        verify=verify,
    )
    print("HTTP {}".format(draft_response.status_code))
    if draft_response.status_code > 201:
        print(draft_response.text)
    draft_response.raise_for_status()
    draft_record: dict[str, Any] = draft_response.json()
    print(draft_record["links"]["self"])
    # publish
    publish_response: requests.Response = requests.post(
        f"https://127.0.0.1:5000/api/records/{draft_record['id']}/draft/actions/publish",
        headers=headers,
        verify=verify,
    )
    print("HTTP {}".format(publish_response.status_code))
    if publish_response.status_code > 201:
        print(publish_response.text)
    publish_response.raise_for_status()
    published_record: dict[str, Any] = publish_response.json()
    print(published_record["links"]["self_html"])

    return published_record


if __name__ == "__main__":
    post()
