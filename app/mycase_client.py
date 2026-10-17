"""
MyCase data-API client - cases and custom fields.

Confirmed against the firm's live Stoplight docs (2026-10-17): base URL,
create/update request+response shapes, and the custom_field_values array
structure are real, not guessed. Two things remain genuinely unconfirmed
(flagged inline as `# TODO CONFIRM`):
  1. The exact path/shape for listing & creating Custom Field definitions
     (needed to resolve a field's *name* to the numeric ID the API wants).
  2. A "staff directory" endpoint to resolve a MyCase staff ID to a name/
     email - the Cases API only ever gives staff IDs + lead/originating
     booleans, never a name. Needed to finish the Staff -> Notion mapping
     in notion_users.py.

Everything else below is real: POST/PUT /cases, the flat (not
case-wrapped) request body, and GET's response shape.
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


def list_matters(page: int = 1) -> list[dict]:
    """TODO CONFIRM: pagination params and envelope shape for GET /cases
    (the individual case shape itself IS confirmed - see get_matter)."""
    _require_api_base()
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{API_BASE}/cases", headers=_headers(), params={"page": page})
        resp.raise_for_status()
        body = resp.json()
    return body.get("cases", body if isinstance(body, list) else [])


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
# TODO CONFIRM: real endpoint. A case's `staff` array only ever gives
# {id, lead_lawyer, originating_lawyer, case_rate, rate_type} - never a
# name or email - so resolving a staff ID to something matchable against
# a Notion user (see notion_users.py) needs a separate "firm users" or
# "staff" listing endpoint. Not yet seen in the docs - screenshot
# whatever lists firm staff members (likely under a "Staff"/"Users"
# section) the same way Cases was done.

_staff_directory_cache: dict[int, dict] = {}  # staff id -> {"name":..., "email":...}


def get_staff_directory() -> dict[int, dict]:
    """TODO CONFIRM path + shape entirely - placeholder until the real
    endpoint is confirmed. Returning {} means Staff/Lead attorney/
    Originating attorney show up with no name until this is wired up -
    logged clearly in sync_engine rather than failing silently."""
    _require_api_base()
    if _staff_directory_cache:
        return _staff_directory_cache
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(f"{API_BASE}/staff", headers=_headers())
            resp.raise_for_status()
            body = resp.json()
        entries = body.get("staff", body if isinstance(body, list) else [])
        for s in entries:
            if s.get("id") is not None:
                _staff_directory_cache[s["id"]] = {"name": s.get("name"), "email": s.get("email")}
    except httpx.HTTPStatusError as exc:
        logger.error("Could not load MyCase staff directory (endpoint unconfirmed): %s", exc)
    return _staff_directory_cache
