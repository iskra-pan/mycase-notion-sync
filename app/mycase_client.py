"""
MyCase data-API client - cases, custom fields, and staff.

Confirmed against the firm's live Stoplight docs (2026-10-17): base URL,
Cases create/update/list, Custom Fields list/create, and the Staff
directory are all real, not guessed - including the flat (not
case-wrapped) request bodies, the custom_field_values array structure,
and cursor-based list pagination via page_size/page_token.

One thing remains an assumption rather than a confirmed fact: the exact
`field_type` string values MyCase's Custom Fields API accepts when
*creating* a field (text_short/text_long/number/checkbox/date/currency,
per MyCase's help-center article - auto-creation in
sync_new_notion_properties_to_mycase is the only code path that depends
on this; reading/writing values on already-existing custom fields doesn't).
"""
import logging
from typing import Optional

import httpx

from app.config import settings
from app.mycase_auth import get_valid_access_token

logger = logging.getLogger("mycase_client")

API_BASE = settings.mycase_api_base  # confirmed default: https://external-integrations.mycase.com/v1


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_valid_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _require_api_base() -> None:
    if not API_BASE:
        raise RuntimeError("MYCASE_API_BASE is not set - see app/config.py.")


def list_matters() -> list[dict]:
    """Confirmed: GET /cases returns a plain array (same convention as
    /custom_fields and /staff), paginated via a `page_token` query param +
    cursor (max page_size 1000, default 25).

    Not yet implementing full cursor pagination - requesting page_size=1000
    in one call covers any realistically-sized firm's open case count.
    Revisit (loop on page_token) if the firm ever has 1000+ cases."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{API_BASE}/cases", headers=_headers(), params={"page_size": 1000})
        resp.raise_for_status()
        return resp.json()


def get_matter(matter_id: str) -> dict:
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{API_BASE}/cases/{matter_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def create_matter(fields: dict, custom_field_values: Optional[list[dict]] = None) -> dict:
    """`fields` uses MyCase's real, confirmed Case keys directly (name,
    case_number, opened_date, closed_date, practice_area, case_stage,
    description, sol_date, status, clients, companies, staff). Do not
    wrap in {"case": ...} - the real API takes a flat body.

    `custom_field_values`, if given: [{"custom_field": {"id": N}, "value": v}, ...]
    - see resolve_custom_field_id() to build this from field names."""
    _require_api_base()
    body = dict(fields)
    if custom_field_values:
        body["custom_field_values"] = custom_field_values
    with httpx.Client(timeout=20) as client:
        resp = client.post(f"{API_BASE}/cases", headers=_headers(), json=body)
        resp.raise_for_status()
        matter = resp.json()
    logger.info("Created MyCase case %s (name=%r)", matter.get("id"), fields.get("name"))
    return matter


def update_matter(matter_id: str, fields: dict, custom_field_values: Optional[list[dict]] = None) -> None:
    """Same flat-body shape as create_matter. Confirmed: this returns
    204 No Content on success - do NOT try to parse a JSON body."""
    _require_api_base()
    body = dict(fields)
    if custom_field_values:
        body["custom_field_values"] = custom_field_values
    with httpx.Client(timeout=20) as client:
        resp = client.put(f"{API_BASE}/cases/{matter_id}", headers=_headers(), json=body)
        resp.raise_for_status()


# --- Custom fields -----------------------------------------------------
#
# Confirmed (2026-10-17): GET/POST https://external-integrations.mycase.com/v1/custom_fields
# List returns a plain JSON array (not wrapped). `parent_type` is "case"
# for the fields this project uses. The exact allowed `field_type` string
# values are still an assumption (text_short/text_long/number/checkbox/
# date/currency, per MyCase's help-center article) - not yet confirmed
# against the API's own validation.

_custom_field_id_cache: dict[str, int] = {}  # name -> id


def list_custom_fields() -> list[dict]:
    """GET /custom_fields returns a plain array: [{id, name, parent_type,
    field_type, list_options, created_at, updated_at}, ...]. page_size
    maxes out at 1000 (default 25) - set explicitly so a firm with more
    than 25 custom fields doesn't silently lose some from the cache."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{API_BASE}/custom_fields", headers=_headers(), params={"page_size": 1000})
        resp.raise_for_status()
        return resp.json()


def resolve_custom_field_id(name: str) -> Optional[int]:
    """Looks up a custom field's numeric ID by its configured name,
    caching the full list on first call. Returns None (logged) if no
    custom field with this name exists in MyCase yet."""
    if not _custom_field_id_cache:
        for f in list_custom_fields():
            if f.get("name"):
                _custom_field_id_cache[f["name"]] = f["id"]
    field_id = _custom_field_id_cache.get(name)
    if field_id is None:
        logger.warning("No MyCase custom field named '%s' found - value not set. "
                        "Create it in MyCase, or let sync_new_notion_properties_to_mycase do it.", name)
    return field_id


def create_custom_field(name: str, field_type: str) -> dict:
    """Used when a brand-new Notion column needs a matching MyCase custom
    field (see sync_engine.sync_new_notion_properties_to_mycase).
    `field_type` values are a TODO CONFIRM assumption - see module note."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            f"{API_BASE}/custom_fields",
            headers=_headers(),
            json={"name": name, "parent_type": "case", "field_type": field_type, "list_options": []},
        )
        resp.raise_for_status()
        field = resp.json()
    _custom_field_id_cache[name] = field["id"]
    logger.warning("Auto-created MyCase custom field '%s' (%s) - verify it looks right in MyCase.", name, field_type)
    return field


# --- Staff directory -----------------------------------------------------
#
# Confirmed (2026-10-17): GET https://external-integrations.mycase.com/v1/staff
# returns a plain array of {id, email, first_name, middle_initial,
# last_name, type, title, active, ...}. This closes the loop for
# Staff/Lead attorney/Originating attorney - a case's staff[] only ever
# gives IDs, this directory resolves each ID to a real name + email.

_staff_directory_cache: dict[int, dict] = {}  # staff id -> {"name":..., "email":...}


def get_staff_directory() -> dict[int, dict]:
    """Cached for the life of the process - staff rosters change rarely.
    Restart the service (or redeploy) to pick up new/changed staff."""
    _require_api_base()
    if _staff_directory_cache:
        return _staff_directory_cache
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{API_BASE}/staff", headers=_headers(), params={"page_size": 1000})
        resp.raise_for_status()
        for s in resp.json():
            if s.get("id") is not None:
                name = " ".join(filter(None, [s.get("first_name"), s.get("last_name")])) or None
                _staff_directory_cache[s["id"]] = {"name": name, "email": s.get("email")}
    return _staff_directory_cache
