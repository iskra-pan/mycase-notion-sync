"""
Resolves MyCase staff to Notion workspace users, so the "Staff" field (a
real Notion "people" property) can be written to safely.

Matches by email ONLY, per the firm's own requirement: "do not guess
ambiguous name matches." Anyone without an email, or without a matching
Notion workspace account, is skipped and logged - never guessed.

Confirmed (2026-10-17): a MyCase case's `staff` array only ever gives
{id, lead_lawyer, originating_lawyer, ...} - never a name or email. So
resolving a staff ID to a Notion user is two hops: MyCase staff ID ->
email (via mycase_client.get_staff_directory - GET /v1/staff, confirmed
real) -> Notion user ID (via the cache below). A staff member with no
email on file in MyCase, or no matching Notion workspace account, is
skipped and logged - never guessed.
"""
import logging
import time
from typing import Optional

from app import mycase_client, notion_client

logger = logging.getLogger("notion_users")

_cache: dict[str, str] = {}  # email (lowercased) -> Notion user id
_cache_loaded_at: float = 0.0
_CACHE_TTL_SECONDS = 3600  # refresh hourly - staff changes are infrequent


def _refresh_cache() -> None:
    global _cache, _cache_loaded_at
    users = notion_client.list_workspace_users()
    cache: dict[str, str] = {}
    for u in users:
        if u.get("type") == "person":
            email = (u.get("person") or {}).get("email")
            if email:
                cache[email.lower()] = u["id"]
    _cache = cache
    _cache_loaded_at = time.time()
    logger.info("Refreshed Notion workspace user cache: %d email-mapped users.", len(_cache))


def get_notion_user_id_by_email(email: str) -> Optional[str]:
    if not email:
        return None
    if not _cache or (time.time() - _cache_loaded_at) > _CACHE_TTL_SECONDS:
        _refresh_cache()
    return _cache.get(email.strip().lower())


def resolve_staff_ids_to_notion_people(mycase_staff_ids: list) -> list[str]:
    """`mycase_staff_ids`: raw MyCase staff IDs, e.g. the `id`s from a
    case's confirmed `staff: [{id, lead_lawyer, originating_lawyer}, ...]`
    array.

    Two-hop resolution: staff ID -> {name, email} via the MyCase staff
    directory, then email -> Notion user ID. Anyone who fails either hop
    (no directory entry, no email, no matching Notion account) is skipped
    and logged - never guessed by name alone.
    """
    if not mycase_staff_ids:
        return []

    directory = mycase_client.get_staff_directory()
    ids = []
    for staff_id in mycase_staff_ids:
        entry = directory.get(staff_id)
        if not entry:
            logger.warning(
                "MyCase staff ID %s not found in the staff directory - skipped "
                "(directory endpoint may still be unconfirmed - see mycase_client.get_staff_directory).",
                staff_id,
            )
            continue
        email = entry.get("email")
        name = entry.get("name", "<unknown>")
        if not email:
            logger.warning("MyCase staff member '%s' (id=%s) has no email - skipped.", name, staff_id)
            continue
        notion_id = get_notion_user_id_by_email(email)
        if notion_id:
            ids.append(notion_id)
        else:
            logger.warning(
                "No Notion workspace member found with email '%s' (MyCase staff: %s) - skipped.",
                email, name,
            )
    return ids
