"""
Declarative Notion <-> MyCase field mapping, matched to the firm's real
"Case Tracking" database (confirmed live via /notion/status).

Edit THIS file (not the sync engine) whenever the firm wants to add or
remove a synced field - nothing syncs unless it has a row here.

Each row says:
  - which Notion database property it comes from
  - which MyCase field it corresponds to (a built-in matter attribute,
    or a MyCase custom field, matched by name)
  - its data type (drives the Notion <-> plain-value conversion)
  - which system is the source of truth when both sides changed between
    syncs - the original brief asked for this to be explicit per field.

Several judgment calls below (source_of_truth defaults, which fields are
"standard" vs "custom") are best-guesses from the schema alone - flagged
with comments. Confirm/adjust them with the firm rather than trusting
them blindly.
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


# --- Core matter attributes ---
# TODO CONFIRM: `mycase_field` values are placeholder key names until
# MyCase's Create/Update Matter schema is confirmed (see mycase_client.py).
#
# No direct equivalent of a separate "Case Manager" exists in the real
# schema (closest is "Assigned Team Members", a people-type field - see
# the excluded list below) - only Lead Attorney maps cleanly.
STANDARD_FIELDS: list[FieldMapping] = [
    FieldMapping("Beneficiary’s Name", "case_name", FieldKind.STANDARD, "title", SourceOfTruth.NOTION),
    FieldMapping("Matter Type", "practice_area", FieldKind.STANDARD, "select", SourceOfTruth.NOTION),
    FieldMapping("Lead Attorney", "attorney", FieldKind.STANDARD, "rich_text", SourceOfTruth.NOTION),
    FieldMapping("Notes", "description", FieldKind.STANDARD, "rich_text", SourceOfTruth.LAST_WRITE_WINS),
    # Default assumption: MyCase is the system of record for case status/
    # billing lifecycle. Flip to NOTION or LAST_WRITE_WINS if the firm
    # actually manages this from Notion instead.
    FieldMapping("Status Category", "status", FieldKind.STANDARD, "select", SourceOfTruth.MYCASE),
]

# --- Custom fields ---
# `mycase_field` must match the custom field's *name* exactly as configured
# in MyCase (Settings -> Custom Fields -> Cases).
CUSTOM_FIELDS: list[FieldMapping] = [
    FieldMapping("Petitioner/Sponsor’s Name", "Petitioner/Sponsor's Name", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION),
    FieldMapping("Filing Deadline", "Filing Deadline", FieldKind.CUSTOM, "date", SourceOfTruth.LAST_WRITE_WINS),
    FieldMapping("Case Open Date", "Case Open Date", FieldKind.CUSTOM, "date", SourceOfTruth.NOTION),
    FieldMapping("Last Activity Date", "Last Activity Date", FieldKind.CUSTOM, "date", SourceOfTruth.LAST_WRITE_WINS),
    FieldMapping("USCIS Receipts #", "USCIS Receipts #", FieldKind.CUSTOM, "rich_text", SourceOfTruth.LAST_WRITE_WINS),
    FieldMapping("Summary", "Summary", FieldKind.CUSTOM, "rich_text", SourceOfTruth.LAST_WRITE_WINS),
    # Firm-internal workflow tracking (~30 stages) - Notion-owned by design;
    # MyCase-side edits to this would be overwritten on the next sync.
    FieldMapping("Stage", "Stage", FieldKind.CUSTOM, "status", SourceOfTruth.NOTION),
]

ALL_FIELDS: list[FieldMapping] = STANDARD_FIELDS + CUSTOM_FIELDS

# The Notion property that stores the MyCase matter link, written back
# after matter creation. The real schema already has this column, as a
# url type (not the generic text property earlier versions of this file
# assumed) - matched to what's actually there.
MATTER_ID_PROPERTY = "MyCase Link"
MATTER_ID_PROPERTY_TYPE = "url"

# --- Deliberately excluded from sync, with reasons (nothing silently dropped) ---
#
# Read-only / Notion-system fields (can't be written via API, not
# meaningful to push anywhere): "Last edited by", "Created by",
# "Created time", "Last edited time".
#
# Formula fields ("Days Until Deadline", "Date of Status Call") - derived,
# read-only in Notion, and this project doesn't yet parse formula-typed
# property values. Add support in notion_values.py first if these turn
# out to be needed in MyCase.
#
# "people"-type fields ("Owner of Next Action", "Assigned Team Members") -
# writing a people property requires mapping names to Notion user IDs,
# not implemented (see notion_values.plain_to_notion_value). Reading them
# into MyCase is possible but held off until there's a confirmed MyCase
# field to put them in.
#
# "Next Action Required" / "Next Action Due Date" - structurally more like
# a MyCase Task (MyCase's API has a separate Tasks resource) than a
# matter-level custom field. Deferred to a future phase that creates/
# updates MyCase tasks instead of shoehorning this into custom fields.
#
# "G-Drive Link" - reserved for the separate Google Drive folder
# automation from the original brief, not part of the MyCase sync.

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
