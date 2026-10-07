"""
Resolves MyCase staff to Notion workspace users, so the "Staff" field (a
real Notion "people" property) can be written to safely.

Matches by email ONLY, per the firm's own requirement: "do not guess
ambiguous name matches." Anyone without an email, or without a matching
Notion workspace account, is skipped and logged - never guessed.

TODO CONFIRM: this assumes MyCase's staff data includes an email per
person, e.g. [{"name": ..., "email": ...}, ...]. Adjust
resolve_staff_to_notion_people() once MyCase's real schema is confirmed -
if MyCase turns out not to expose staff emails at all, real per-person
matching isn't possible and "Staff" should be converted to a Notion Text
property instead (synced as a plain display string), per the firm's own
documented fallback.
"""
import logging
import time
from typing import Optional

from app import notion_client

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


def resolve_staff_to_notion_people(mycase_staff: list) -> list[str]:
    """`mycase_staff`: whatever MyCase's API returns for a case's staff
    list - TODO CONFIRM the real shape; assumed to be a list of
    {"name": ..., "email": ...} dicts for now.

    Returns Notion user IDs for staff matched confidently by email.
    Everyone else is skipped and logged - never guessed by name alone.
    """
    if not mycase_staff:
        return []

    ids = []
    for person in mycase_staff:
        if not isinstance(person, dict):
            logger.warning("Unexpected MyCase staff entry shape (not a dict): %r - skipped.", person)
            continue
        name = person.get("name", "<unknown>")
        email = person.get("email")
        if not email:
            logger.warning(
                "MyCase staff member '%s' has no email in the API response - skipped "
                "(can't safely match to a Notion user without one).", name,
            )
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
