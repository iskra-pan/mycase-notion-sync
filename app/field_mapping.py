"""
Declarative Notion <-> MyCase field mapping.

Edit THIS file (not the sync engine) whenever the firm wants to add or
remove a synced field - nothing syncs unless it has a row here.

Each row says:
  - which Notion database property it comes from
  - which MyCase field it corresponds to (a built-in matter attribute,
    or a MyCase custom field, matched by name)
  - its data type (drives the Notion <-> plain-value conversion)
  - which system is the source of truth when both sides changed between
    syncs - the original brief asked for this to be explicit per field.
"""
from dataclasses import dataclass
from enum import Enum


class SourceOfTruth(str, Enum):
    NOTION = "notion"                    # Notion always wins; MyCase is overwritten to match
    MYCASE = "mycase"                    # MyCase always wins; Notion is overwritten to match
    LAST_WRITE_WINS = "last_write_wins"  # whichever side was edited more recently wins


class FieldKind(str, Enum):
    STANDARD = "standard"  # a built-in MyCase matter attribute (name, status, ...)
    CUSTOM = "custom"      # a MyCase custom field, matched to Notion by name


@dataclass(frozen=True)
class FieldMapping:
    notion_property: str   # exact Notion database column name
    mycase_field: str      # MyCase attribute key (standard) or custom field name (custom)
    kind: FieldKind
    notion_type: str       # Notion property type: title | rich_text | email | phone_number | date | select | status | number | checkbox | people | url
    source_of_truth: SourceOfTruth = SourceOfTruth.LAST_WRITE_WINS


# --- Core matter attributes, per the brief's "at least the main fields" ---
# TODO CONFIRM: the `mycase_field` values are placeholder key names until
# MyCase's Create/Update Matter schema is confirmed (see mycase_client.py).
STANDARD_FIELDS: list[FieldMapping] = [
    FieldMapping("Client Name", "case_name", FieldKind.STANDARD, "title", SourceOfTruth.NOTION),
    FieldMapping("Matter Type", "practice_area", FieldKind.STANDARD, "select", SourceOfTruth.NOTION),
    FieldMapping("Attorney", "attorney", FieldKind.STANDARD, "people", SourceOfTruth.NOTION),
    FieldMapping("Case Manager", "case_manager", FieldKind.STANDARD, "people", SourceOfTruth.NOTION),
    FieldMapping("Notes", "description", FieldKind.STANDARD, "rich_text", SourceOfTruth.LAST_WRITE_WINS),
    FieldMapping("Status", "status", FieldKind.STANDARD, "select", SourceOfTruth.MYCASE),
]

# --- Custom fields: email, dates, contact info, etc. ---
# `mycase_field` must match the custom field's *name* exactly as configured
# in MyCase (Settings -> Custom Fields -> Cases).
CUSTOM_FIELDS: list[FieldMapping] = [
    FieldMapping("Client Email", "Client Email", FieldKind.CUSTOM, "email", SourceOfTruth.NOTION),
    FieldMapping("Client Phone", "Client Phone", FieldKind.CUSTOM, "phone_number", SourceOfTruth.NOTION),
    FieldMapping("Filing Date", "Filing Date", FieldKind.CUSTOM, "date", SourceOfTruth.LAST_WRITE_WINS),
    FieldMapping("Next Hearing Date", "Next Hearing Date", FieldKind.CUSTOM, "date", SourceOfTruth.LAST_WRITE_WINS),
    # Add one row per additional field you want synced.
]

ALL_FIELDS: list[FieldMapping] = STANDARD_FIELDS + CUSTOM_FIELDS

# The Notion property (added once, manually, to the database - see README)
# that stores the MyCase Matter ID/link written back after matter creation.
MATTER_ID_PROPERTY = "MyCase Matter ID"

# Notion property type -> best-fit MyCase custom field type, used only when
# auto-creating a MyCase custom field for a brand-new Notion column. Notion
# types with no sane MyCase equivalent (relation, formula, rollup, files,
# people, etc.) are deliberately left out - those are skipped with a
# warning rather than silently mis-mapped.
NOTION_TYPE_TO_MYCASE_CUSTOM_FIELD_TYPE = {
    "rich_text": "text_long",
    "title": "text_short",
    "email": "text_short",
    "phone_number": "text_short",
    "url": "text_short",
    "number": "number",
    "checkbox": "checkbox",
    "date": "date",
    "select": "text_short",
    "status": "text_short",
}
