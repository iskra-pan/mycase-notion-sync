"""
Thin wrapper around the Notion API.

Uses a static internal-integration token (Notion -> Settings -> Connections
-> Develop or manage integrations -> New integration), NOT OAuth - correct
for a single firm syncing its own workspace. Docs:
https://developers.notion.com/reference

Pinned to API version 2022-06-28: it's the long-stable contract for
database query/update and page property read/write, unaffected by the
2025-09-03 "data sources" restructuring. Upgrading later (e.g. to use the
newer webhook event types) is a deliberate choice, not a default.
"""
from typing import Optional

import httpx

from app.config import settings

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def query_database(filter_after: Optional[str] = None) -> list[dict]:
    """All pages in the tracked database, optionally only those last-edited
    after the given ISO 8601 timestamp (used for polling)."""
    payload: dict = {"page_size": 100}
    if filter_after:
        payload["filter"] = {
            "timestamp": "last_edited_time",
            "last_edited_time": {"after": filter_after},
        }
        payload["sorts"] = [{"timestamp": "last_edited_time", "direction": "ascending"}]

    url = f"{BASE_URL}/databases/{settings.notion_database_id}/query"
    pages: list[dict] = []
    with httpx.Client(timeout=15) as client:
        while True:
            resp = client.post(url, headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
            pages.extend(data["results"])
            if not data.get("has_more"):
                break
            payload["start_cursor"] = data["next_cursor"]
    return pages


def get_page(page_id: str) -> dict:
    with httpx.Client(timeout=15) as client:
        resp = client.get(f"{BASE_URL}/pages/{page_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def update_page_properties(page_id: str, properties: dict) -> dict:
    """`properties` uses Notion's property-value shape per property name,
    e.g. {"Status": {"select": {"name": "Open"}}} - see notion_values.py."""
    with httpx.Client(timeout=15) as client:
        resp = client.patch(
            f"{BASE_URL}/pages/{page_id}",
            headers=_headers(),
            json={"properties": properties},
        )
        resp.raise_for_status()
        return resp.json()


def get_database_schema() -> dict:
    """{property_name: property_type} for the tracked database."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(f"{BASE_URL}/databases/{settings.notion_database_id}", headers=_headers())
        resp.raise_for_status()
        data = resp.json()
    return {name: prop["type"] for name, prop in data["properties"].items()}


def add_database_property(name: str, notion_type: str) -> None:
    """Add a new column to the Notion database (used when a MyCase custom
    field has no Notion counterpart yet)."""
    type_config = {
        "rich_text": {}, "number": {"format": "number"}, "checkbox": {},
        "date": {}, "email": {}, "phone_number": {}, "url": {},
        "select": {"options": []},
    }.get(notion_type, {})
    with httpx.Client(timeout=15) as client:
        resp = client.patch(
            f"{BASE_URL}/databases/{settings.notion_database_id}",
            headers=_headers(),
            json={"properties": {name: {notion_type: type_config}}},
        )
        resp.raise_for_status()
