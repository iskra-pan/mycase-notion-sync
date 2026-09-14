"""
Generic document storage, backed by Firestore in production.

Cloud Run instances are stateless and can scale to N copies, so state
can't live in memory or on local disk in production - it must live
somewhere shared. Firestore is used for:
  - oauth_tokens/mycase        the MyCase OAuth token pair
  - case_mappings/<notion_id>  Notion page <-> MyCase matter, per case
  - poll_cursors/<key>         "last successfully polled up to" timestamps

For local development without GCP credentials configured, everything
falls back to a single local JSON file so you can test without a GCP
project. That fallback is dev-only - it will NOT work correctly on
Cloud Run (each instance/restart has its own throwaway disk).
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional, TypedDict

from app.config import settings

logger = logging.getLogger("storage")

_LOCAL_FALLBACK_PATH = Path(__file__).resolve().parent.parent / ".local_store.json"


def _firestore_client():
    if not settings.gcp_project_id:
        return None
    try:
        from google.cloud import firestore
        return firestore.Client(project=settings.gcp_project_id)
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Firestore unavailable (%s); falling back to local file store.", exc)
        return None


def _load_local() -> dict:
    if _LOCAL_FALLBACK_PATH.exists():
        return json.loads(_LOCAL_FALLBACK_PATH.read_text())
    return {}


def _save_local(data: dict) -> None:
    _LOCAL_FALLBACK_PATH.write_text(json.dumps(data, indent=2))


def get_doc(collection: str, doc_id: str) -> Optional[dict]:
    client = _firestore_client()
    if client:
        snap = client.collection(collection).document(doc_id).get()
        return snap.to_dict() if snap.exists else None
    return _load_local().get(collection, {}).get(doc_id)


def set_doc(collection: str, doc_id: str, data: dict) -> None:
    client = _firestore_client()
    if client:
        client.collection(collection).document(doc_id).set(data)
        return
    store = _load_local()
    store.setdefault(collection, {})[doc_id] = data
    _save_local(store)


def list_docs(collection: str) -> list[dict]:
    client = _firestore_client()
    if client:
        return [d.to_dict() for d in client.collection(collection).stream()]
    return list(_load_local().get(collection, {}).values())


# --- MyCase OAuth tokens -----------------------------------------------

class TokenRecord(TypedDict):
    access_token: str
    refresh_token: str
    expires_at: float  # unix timestamp


def save_mycase_tokens(access_token: str, refresh_token: str, expires_in: int) -> None:
    record: TokenRecord = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in,
    }
    set_doc("oauth_tokens", "mycase", record)


def load_mycase_tokens() -> Optional[TokenRecord]:
    return get_doc("oauth_tokens", "mycase")  # type: ignore[return-value]


# --- Notion <-> MyCase case mapping -------------------------------------

def save_case_mapping(notion_page_id: str, mycase_matter_id: str, extra: Optional[dict] = None) -> None:
    record = {"notion_page_id": notion_page_id, "mycase_matter_id": mycase_matter_id, **(extra or {})}
    set_doc("case_mappings", notion_page_id, record)


def get_case_mapping_by_notion_page(notion_page_id: str) -> Optional[dict]:
    return get_doc("case_mappings", notion_page_id)


def get_case_mapping_by_mycase_matter(mycase_matter_id: str) -> Optional[dict]:
    for record in list_docs("case_mappings"):
        if record.get("mycase_matter_id") == mycase_matter_id:
            return record
    return None


# --- Poll cursors ---------------------------------------------------------

def get_last_poll_timestamp(key: str) -> Optional[str]:
    doc = get_doc("poll_cursors", key)
    return doc["timestamp"] if doc else None


def set_last_poll_timestamp(key: str, timestamp: str) -> None:
    set_doc("poll_cursors", key, {"timestamp": timestamp})
