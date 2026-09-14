"""
MyCase data-API client - matters (cases) and custom fields.

STATUS: scaffolded, NOT yet verified against MyCase's live schema.

MyCase's docs (https://mycaseapi.stoplight.io) render client-side (JS), so
this project's fetch tooling could only ever confirm the page titles, not
the JSON schema underneath, even though the same pages render fine in a
real browser. The OAuth mechanics in mycase_auth.py ARE confirmed (pulled
from live docs successfully). Everything below is a best-effort,
clean-interface placeholder - realistic REST conventions, not confirmed
fact. Treat every `# TODO CONFIRM` as blocking before this touches real
firm data.

To finish wiring this up:
  1. Set MYCASE_API_BASE (env var) once you know the real data-API host -
     auth.mycase.com is documented as the OAuth host only; the resource
     API is very likely a different host.
  2. Open MyCase's docs for "Cases" (create/update) and "Custom Fields" in
     your own browser (or ask MyCase support for a Postman collection,
     which most API providers hand out with credentials) and paste me the
     JSON field names - I'll fix the payload builders below in minutes.
  3. Create one throwaway matter through this client against a MyCase
     sandbox/test account before wiring it into the live sync loop.

Nothing in field_mapping.py, sync_engine.py, or storage.py needs to change
when you fix the details here - only this file's paths/payload keys do.
"""
import logging

import httpx

from app.config import settings
from app.mycase_auth import get_valid_access_token

logger = logging.getLogger("mycase_client")

# TODO CONFIRM: real data-API host.
API_BASE = settings.mycase_api_base


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_valid_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _require_api_base() -> None:
    if not API_BASE:
        raise RuntimeError(
            "MYCASE_API_BASE is not set. This is the one piece of the MyCase "
            "data API this project could not confirm automatically - see the "
            "module docstring in app/mycase_client.py for how to get it."
        )


def list_matters(page: int = 1) -> list[dict]:
    """TODO CONFIRM: path, pagination params, response envelope."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{API_BASE}/cases", headers=_headers(), params={"page": page})
        resp.raise_for_status()
        body = resp.json()
    # TODO CONFIRM: is the list under body["cases"], body["data"], or is
    # `body` itself the list? Adjust once confirmed.
    return body.get("cases", body if isinstance(body, list) else [])


def get_matter(matter_id: str) -> dict:
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{API_BASE}/cases/{matter_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def create_matter(fields: dict) -> dict:
    """`fields` are plain values keyed by the STANDARD_FIELDS mycase_field
    names from field_mapping.py, e.g. {"case_name": ..., "practice_area": ...}.
    TODO CONFIRM the exact JSON keys MyCase expects for matter creation."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.post(f"{API_BASE}/cases", headers=_headers(), json={"case": fields})
        resp.raise_for_status()
        matter = resp.json()
    logger.info("Created MyCase matter for fields=%s -> %s", fields, matter)
    return matter


def update_matter(matter_id: str, fields: dict) -> dict:
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.put(f"{API_BASE}/cases/{matter_id}", headers=_headers(), json={"case": fields})
        resp.raise_for_status()
        return resp.json()


def list_custom_fields() -> list[dict]:
    """TODO CONFIRM path + shape. Expected: [{"id":.., "name":.., "field_type":..}, ...]."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{API_BASE}/custom_fields", headers=_headers())
        resp.raise_for_status()
        body = resp.json()
    return body.get("custom_fields", body if isinstance(body, list) else [])


def create_custom_field(name: str, field_type: str) -> dict:
    """Used when a brand-new Notion column needs a matching MyCase custom
    field (see sync_engine.sync_new_notion_properties_to_mycase).
    TODO CONFIRM path/payload keys, and MyCase's exact field_type values
    (this project assumes text_short/text_long/number/checkbox/date/currency
    per MyCase's help-center article on custom field types - not yet
    confirmed against the API itself)."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            f"{API_BASE}/custom_fields",
            headers=_headers(),
            json={"custom_field": {"name": name, "field_type": field_type, "resource": "case"}},
        )
        resp.raise_for_status()
        field = resp.json()
    logger.warning("Auto-created MyCase custom field '%s' (%s) - verify it looks right in MyCase.", name, field_type)
    return field


def set_custom_field_value(matter_id: str, field_name: str, value) -> None:
    """TODO CONFIRM: whether custom field values are set via the matter
    update payload's `custom_field_values` array (assumed here) or a
    separate per-value endpoint."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.put(
            f"{API_BASE}/cases/{matter_id}",
            headers=_headers(),
            json={"case": {"custom_field_values": [{"name": field_name, "value": value}]}},
        )
        resp.raise_for_status()
