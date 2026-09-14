"""
Two-way sync orchestration between Notion and MyCase.

Runs on a schedule (Cloud Scheduler -> the endpoints in sync_routes.py),
not on live webhooks. Polling alone satisfies every requirement in the
brief (create on new Notion page, push changes both ways, propagate new
Notion columns as MyCase custom fields) with a few minutes of latency
instead of instant - simpler and more robust than standing up two
different providers' webhook-verification handshakes. Real-time push is a
fine phase-3 upgrade once this is proven reliable; it is not needed to
meet the brief.

Conflict rule per field, from field_mapping.SourceOfTruth:
  - NOTION: Notion always wins; MyCase is overwritten to match.
  - MYCASE: MyCase always wins; Notion is overwritten to match.
  - LAST_WRITE_WINS: whichever side has the more recent edit timestamp wins.
"""
import logging
from datetime import datetime, timezone

from app import mycase_client, notion_client
from app.field_mapping import (
    ALL_FIELDS,
    CUSTOM_FIELDS,
    MATTER_ID_PROPERTY,
    NOTION_TYPE_TO_MYCASE_CUSTOM_FIELD_TYPE,
    STANDARD_FIELDS,
    FieldKind,
    SourceOfTruth,
)
from app.notion_values import notion_value_to_plain, plain_to_notion_value
from app.storage import (
    get_case_mapping_by_mycase_matter,
    get_case_mapping_by_notion_page,
    get_last_poll_timestamp,
    save_case_mapping,
    set_last_poll_timestamp,
)

logger = logging.getLogger("sync_engine")

_MAPPED_NOTION_PROPERTIES = {f.notion_property for f in ALL_FIELDS}


def sync_new_and_changed_notion_pages() -> dict:
    """Poll Notion for pages created/edited since the last run; create or
    update the matching MyCase matter for each."""
    since = get_last_poll_timestamp("notion")
    poll_started_at = datetime.now(timezone.utc).isoformat()
    pages = notion_client.query_database(filter_after=since)

    created = updated = failed = 0
    for page in pages:
        try:
            if _sync_one_notion_page(page) == "created":
                created += 1
            else:
                updated += 1
        except Exception:
            logger.exception("Failed syncing Notion page %s", page["id"])
            failed += 1

    set_last_poll_timestamp("notion", poll_started_at)
    return {"seen": len(pages), "created": created, "updated": updated, "failed": failed}


def _sync_one_notion_page(page: dict) -> str:
    page_id = page["id"]
    props = page["properties"]
    notion_edited_at = page["last_edited_time"]

    plain_values = {
        f: notion_value_to_plain(f.notion_type, props.get(f.notion_property))
        for f in ALL_FIELDS
    }

    mapping = get_case_mapping_by_notion_page(page_id)

    if mapping is None:
        return _create_mycase_matter_for_page(page_id, notion_edited_at, plain_values)

    return _push_notion_changes_to_mycase(mapping, notion_edited_at, plain_values)


def _create_mycase_matter_for_page(page_id: str, notion_edited_at: str, plain_values: dict) -> str:
    standard_fields = {f.mycase_field: plain_values[f] for f in STANDARD_FIELDS}
    matter = mycase_client.create_matter(standard_fields)
    # TODO CONFIRM: the real key for the new matter's ID in MyCase's response.
    matter_id = str(matter.get("id") or matter.get("case", {}).get("id"))

    for f in CUSTOM_FIELDS:
        if plain_values[f] is not None:
            mycase_client.set_custom_field_value(matter_id, f.mycase_field, plain_values[f])

    save_case_mapping(page_id, matter_id, {
        "notion_edited_at": notion_edited_at,
        "mycase_edited_at": None,
    })

    # Write the Matter ID back onto the Notion page, per the brief.
    notion_client.update_page_properties(page_id, {
        MATTER_ID_PROPERTY: plain_to_notion_value("rich_text", matter_id),
    })
    logger.info("Notion page %s -> created MyCase matter %s", page_id, matter_id)
    return "created"


def _push_notion_changes_to_mycase(mapping: dict, notion_edited_at: str, plain_values: dict) -> str:
    matter_id = mapping["mycase_matter_id"]
    mycase_edited_at = mapping.get("mycase_edited_at")

    to_push = {}
    for f in ALL_FIELDS:
        if f.source_of_truth == SourceOfTruth.MYCASE:
            continue
        if (
            f.source_of_truth == SourceOfTruth.LAST_WRITE_WINS
            and mycase_edited_at
            and mycase_edited_at > notion_edited_at
        ):
            continue  # MyCase's edit is newer for this field - don't clobber it
        to_push[f] = plain_values[f]

    standard_updates = {f.mycase_field: v for f, v in to_push.items() if f.kind == FieldKind.STANDARD}
    if standard_updates:
        mycase_client.update_matter(matter_id, standard_updates)

    for f, v in to_push.items():
        if f.kind == FieldKind.CUSTOM and v is not None:
            mycase_client.set_custom_field_value(matter_id, f.mycase_field, v)

    save_case_mapping(mapping["notion_page_id"], matter_id, {
        "notion_edited_at": notion_edited_at,
        "mycase_edited_at": mycase_edited_at,
    })
    return "updated"


def sync_changed_mycase_matters() -> dict:
    """Poll MyCase for matters updated since last run; push non-Notion-owned
    field changes to the matching Notion page. Matters with no mapping
    (created directly in MyCase, not via Notion) are out of scope per the
    brief and are skipped."""
    matters = mycase_client.list_matters()
    updated = 0
    for m in matters:
        # TODO CONFIRM: real key names for matter id / updated-at timestamp.
        matter_id = str(m["id"])
        mycase_edited_at = m.get("updated_at")

        mapping = get_case_mapping_by_mycase_matter(matter_id)
        if mapping is None:
            continue
        if mapping.get("mycase_edited_at") == mycase_edited_at:
            continue  # unchanged since last poll

        notion_updates = {}
        for f in ALL_FIELDS:
            if f.source_of_truth == SourceOfTruth.NOTION:
                continue
            value = m.get(f.mycase_field)
            try:
                notion_updates[f.notion_property] = plain_to_notion_value(f.notion_type, value)
            except ValueError:
                logger.warning("Skipping write-back for '%s' (%s): %s", f.notion_property, f.notion_type, value)

        if notion_updates:
            notion_client.update_page_properties(mapping["notion_page_id"], notion_updates)

        save_case_mapping(mapping["notion_page_id"], matter_id, {
            "notion_edited_at": mapping.get("notion_edited_at"),
            "mycase_edited_at": mycase_edited_at,
        })
        updated += 1

    return {"seen": len(matters), "updated": updated}


def sync_new_notion_properties_to_mycase() -> dict:
    """Detect Notion database columns with no MyCase custom field mapped
    yet, and auto-create a matching custom field in MyCase. Run this far
    less often than the data sync (e.g. hourly) - schema changes are rare,
    and each new field still needs a row added to CUSTOM_FIELDS in
    field_mapping.py before its *values* start syncing (creating the field
    is automatic; wiring its data is a deliberate one-line step)."""
    schema = notion_client.get_database_schema()
    created, skipped = [], []

    for prop_name, prop_type in schema.items():
        if prop_name in _MAPPED_NOTION_PROPERTIES or prop_name == MATTER_ID_PROPERTY:
            continue
        mycase_type = NOTION_TYPE_TO_MYCASE_CUSTOM_FIELD_TYPE.get(prop_type)
        if mycase_type is None:
            skipped.append({"property": prop_name, "notion_type": prop_type})
            continue
        mycase_client.create_custom_field(prop_name, mycase_type)
        created.append(prop_name)
        logger.warning(
            "Auto-created MyCase custom field '%s' for new Notion property. "
            "Add a row to CUSTOM_FIELDS in field_mapping.py to start syncing its values.",
            prop_name,
        )

    if skipped:
        logger.warning("Skipped auto-creating MyCase fields for unsupported Notion types: %s", skipped)
    return {"created": created, "skipped": skipped}
