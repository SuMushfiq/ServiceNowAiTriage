"""
Thin wrapper around the ServiceNow Table API for the incident table.
Docs: https://docs.servicenow.com/bundle/latest-release-notes/page/integrate/inbound-rest/concept/c_TableAPI.html
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

SNOW_INSTANCE = os.environ["SNOW_INSTANCE"].rstrip("/")
SNOW_AUTH = (os.environ["SNOW_USERNAME"], os.environ["SNOW_PASSWORD"])
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


def get_open_incidents(limit: int = 20) -> list[dict]:
    """Fetch open incidents that haven't been AI-triaged yet.

    We use a custom field-free approach here: incidents where the
    work_notes don't yet contain our marker string. In a real ServiceNow
    setup you'd add a proper 'u_ai_triaged' boolean field instead -
    this keeps the starter code to a single table with no schema changes.
    """
    url = f"{SNOW_INSTANCE}/api/now/table/incident"
    params = {
        "sysparm_query": "active=true^stateNOT IN6,7",  # not resolved/closed
        "sysparm_limit": limit,
        "sysparm_fields": "sys_id,number,short_description,description,category,priority,urgency,impact,work_notes",
        "sysparm_display_value": "true",
    }
    resp = requests.get(url, auth=SNOW_AUTH, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]


def update_incident(sys_id: str, fields: dict) -> dict:
    """PATCH an incident with new field values (category, priority, etc)."""
    url = f"{SNOW_INSTANCE}/api/now/table/incident/{sys_id}"
    resp = requests.patch(url, auth=SNOW_AUTH, headers=HEADERS, json=fields, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]


def add_work_note(sys_id: str, note: str) -> dict:
    """Append a work note to an incident (used for AI suggestions + audit trail)."""
    return update_incident(sys_id, {"work_notes": note})


def create_test_incident(short_description: str, description: str) -> dict:
    """Helper for seeding test data into your PDI so you have something to triage."""
    url = f"{SNOW_INSTANCE}/api/now/table/incident"
    payload = {"short_description": short_description, "description": description}
    resp = requests.post(url, auth=SNOW_AUTH, headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]
