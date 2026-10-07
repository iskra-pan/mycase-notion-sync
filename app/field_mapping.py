"""
Declarative Notion <-> MyCase field mapping, matched to the firm's real
"Case Tracking" database (confirmed live via /notion/status, 2026-10-07)
and the firm's own MyCase field inventory.

Edit THIS file (not the sync engine) whenever the firm wants to add or
remove a synced field - nothing syncs unless it has a row here.

Almost every field below defaults to source_of_truth=MYCASE, per the
firm's own field descriptions ("mirror MyCase's value", "display the
MyCase X"). Practical effect: a brand-new Notion page still creates the
MyCase matter using whatever is typed in Notion at creation time, but
*after* that, edits to these fields in Notion do NOT push back to
MyCase - only MyCase -> Notion flows. If that's not the intended
workflow for some of these fields, change their source_of_truth.

`mycase_field` values for STANDARD_FIELDS are placeholder snake_case
keys - TODO CONFIRM against MyCase's real Case API schema (see
mycase_client.py). `mycase_field` values for CUSTOM_FIELDS reuse the
Notion property name, on the assumption the firm named the MyCase
custom field the same way - also TODO CONFIRM.
"""
from dataclasses import dataclass
from enum import Enum


class SourceOfTruth(str, Enum):
    NOTION = "notion"                    # Notion always wins; MyCase is overwritten to match
    MYCASE = "mycase"                    # MyCase always wins; Notion is overwritten to match
    LAST_WRITE_WINS = "last_write_wins"  # whichever side was edited more recently wins


class FieldKind(str, Enum):
    STANDARD = "standard"  # a built-in MyCase matter/case attribute
    CUSTOM = "custom"      # a MyCase custom field, matched to Notion by name


@dataclass(frozen=True)
class FieldMapping:
    notion_property: str   # exact Notion database column name
    mycase_field: str      # MyCase attribute key (standard) or custom field name (custom)
    kind: FieldKind
    notion_type: str       # title | rich_text | email | phone_number | date | select | status | number | checkbox | people | url
    source_of_truth: SourceOfTruth = SourceOfTruth.LAST_WRITE_WINS
    note: str = ""         # the firm's own handling note for this field, kept alongside the code


# =====================================================================
# Case Overview and Case Information  ->  MyCase's built-in case fields
# =====================================================================
STANDARD_FIELDS: list[FieldMapping] = [
    FieldMapping("Name", "case_name", FieldKind.STANDARD, "title", SourceOfTruth.MYCASE,
                 "Use the complete MyCase case name. Do not substitute only the beneficiary's name."),
    FieldMapping("Case Number", "case_number", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Preserve the exact value, including leading zeros."),
    FieldMapping("Contacts", "contacts", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Display all linked MyCase contact names. Never create/replace contacts by name alone."),
    FieldMapping("Date Opened", "date_opened", FieldKind.STANDARD, "date", SourceOfTruth.MYCASE,
                 "Copy the source date without timezone-related day shifts."),
    FieldMapping("Date Closed", "date_closed", FieldKind.STANDARD, "date", SourceOfTruth.MYCASE,
                 "Leave blank when no date exists."),
    FieldMapping("Practice Area", "practice_area", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Open question: should this become a Select field?"),
    # NOTE: the firm's doc describes this as a Notion "Status" type, but the
    # live database has it as "select" - built against what's actually live.
    FieldMapping("Case Stage", "case_stage", FieldKind.STANDARD, "select", SourceOfTruth.MYCASE,
                 "Match the complete MyCase stage list and spelling; verify Notion's Select options cover all of them."),
    FieldMapping("Office", "office", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE, ""),
    FieldMapping("Lead attorney", "lead_attorney", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Display only - no write-back (would need MyCase user ID resolution)."),
    FieldMapping("Originating attorney", "originating_attorney", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Display only - no write-back."),
    # Real Notion "people" property - resolved by email via
    # app/notion_users.py, never guessed from a name. Staff with no email
    # from MyCase, or no matching Notion account, are skipped and logged
    # rather than written incorrectly.
    FieldMapping("Staff", "staff", FieldKind.STANDARD, "people", SourceOfTruth.MYCASE,
                 "Multiple staff members supported. Matched to Notion users by email only."),
    FieldMapping("Created", "created_info", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "MyCase's own creation date/creator as data - not Notion's system creation metadata."),
    FieldMapping("Description", "description", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Preserve line breaks and supported formatting."),
    FieldMapping("Conflict Check", "conflict_check", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Open question: confirm MyCase's real type (Text/Select/Checkbox) before relying on this."),
    FieldMapping("Conflict Check Notes", "conflict_check_notes", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Preserve line breaks."),
]

# =====================================================================
# Custom Fields  ->  MyCase custom_field_values
# =====================================================================
CUSTOM_FIELDS: list[FieldMapping] = [
    FieldMapping("Email", "Email", FieldKind.CUSTOM, "email", SourceOfTruth.MYCASE,
                 "The case-level custom Email field, not a contact's email."),
    FieldMapping("Phone", "Phone", FieldKind.CUSTOM, "phone_number", SourceOfTruth.MYCASE,
                 "Preserve country code, extension, and exact source formatting."),
    FieldMapping("Date Added", "Date Added", FieldKind.CUSTOM, "date", SourceOfTruth.MYCASE,
                 "Keep separate from Date Opened and Created."),
    FieldMapping("Lead Type", "Lead Type", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Open question: confirm source type and full option list if it's a dropdown."),
    FieldMapping("Lead Source", "Lead Source", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Open question: confirm dropdown options if applicable."),
    FieldMapping("Case Type", "Case Type", FieldKind.CUSTOM, "select", SourceOfTruth.MYCASE,
                 "Notion's current Select options are not a verified complete list of MyCase's options."),
    FieldMapping("G-Drive link", "G-Drive link", FieldKind.CUSTOM, "url", SourceOfTruth.MYCASE,
                 "Likely superseded once the separate Google Drive folder automation is built."),
    FieldMapping("USCIS Receipt Number - 1", "USCIS Receipt Number - 1", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Keep separate from receipt number 2."),
    FieldMapping("USCIS Receipt Number - 2", "USCIS Receipt Number - 2", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Keep separate from receipt number 1."),

    # Filing/expense slots 1-4. NOTE: slot 2's "Type of Filing" has a
    # capital F (unlike slots 1/3/4's "Type of filing") - this is the
    # firm's real property name, not a typo - preserved exactly.
    FieldMapping("1 Filing — Type of filing", "1 Filing — Type of filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE, ""),
    FieldMapping("1 Filing — Date", "1 Filing — Date", FieldKind.CUSTOM, "date", SourceOfTruth.MYCASE, ""),
    FieldMapping("1 Filing — Card", "1 Filing — Card", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Card label/reference only - never full card numbers or security codes."),
    FieldMapping("1 Filing — Amount", "1 Filing — Amount", FieldKind.CUSTOM, "number", SourceOfTruth.MYCASE,
                 "Open question: confirm currency and decimal precision."),

    FieldMapping("2 Filing — Type of Filing", "2 Filing — Type of Filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE, ""),
    FieldMapping("2 Filing — Date", "2 Filing — Date", FieldKind.CUSTOM, "date", SourceOfTruth.MYCASE, ""),
    FieldMapping("2 Filing — Amount", "2 Filing — Amount", FieldKind.CUSTOM, "number", SourceOfTruth.MYCASE, ""),
    FieldMapping("2 Filing — Card", "2 Filing — Card", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Card label/reference only."),

    FieldMapping("3 Filing/Expenses — Type of filing", "3 Filing/Expenses — Type of filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE, ""),
    FieldMapping("3 Filing/Expenses — Date", "3 Filing/Expenses — Date", FieldKind.CUSTOM, "date", SourceOfTruth.MYCASE, ""),
    FieldMapping("3 Filing/Expenses — Amount", "3 Filing/Expenses — Amount", FieldKind.CUSTOM, "number", SourceOfTruth.MYCASE, ""),
    FieldMapping("3 Filing/Expenses — Card", "3 Filing/Expenses — Card", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Card label/reference only."),

    FieldMapping("4 Filing/Expenses — Type of filing", "4 Filing/Expenses — Type of filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE, ""),
    FieldMapping("4 Filing/Expenses — Date", "4 Filing/Expenses — Date", FieldKind.CUSTOM, "date", SourceOfTruth.MYCASE, ""),
    FieldMapping("4 Filing/Expenses — Amount", "4 Filing/Expenses — Amount", FieldKind.CUSTOM, "number", SourceOfTruth.MYCASE, ""),
    FieldMapping("4 Filing/Expenses — Card", "4 Filing/Expenses — Card", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Card label/reference only."),

    FieldMapping("Filing notes", "Filing notes", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE, ""),
    FieldMapping("Billing transferred", "Billing transferred", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Open question: confirm whether the MyCase source is actually a checkbox/date/dropdown/text."),
    FieldMapping("Payment arrangements if any:", "Payment arrangements if any:", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Exact property name includes the trailing colon."),
    FieldMapping("Date — Requested to Close", "Date — Requested to Close", FieldKind.CUSTOM, "date", SourceOfTruth.MYCASE,
                 "A closure *request* date - keep separate from the actual Date Closed."),
    FieldMapping("Payment status for filing", "Payment status for filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Open question: confirm dropdown options if applicable."),
    FieldMapping("Case Manager", "Case Manager", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Display only - no write-back (would need MyCase user ID resolution)."),
    FieldMapping("Main Status", "Main Status", FieldKind.CUSTOM, "rich_text", SourceOfTruth.MYCASE,
                 "Separate concept from Case Stage. Open question: confirm the complete MyCase status options."),
]

ALL_FIELDS: list[FieldMapping] = STANDARD_FIELDS + CUSTOM_FIELDS

# "MyCase Link" is NOT one of MyCase's own fields being mirrored - it's
# generated by this app after matching/creating a matter, and written back
# to Notion. Normally read-only from the sync's perspective.
MATTER_ID_PROPERTY = "MyCase Link"
MATTER_ID_PROPERTY_TYPE = "url"

# --- Deliberately excluded from sync, with reasons (nothing silently dropped) ---
#
# "Staff" is now wired up (see app/notion_users.py) - matched to Notion
# users by email, never by guessing names. One real dependency remains:
# this only works once MyCase's API is confirmed to actually include an
# email per staff member (see mycase_client.py). If it turns out MyCase
# only gives names, per-person matching isn't safely possible and the
# firm's own documented fallback applies instead: convert "Staff" from a
# Person property to a Text property in Notion, and sync it as a plain
# display string of names (one-line change in notion_type + the
# resolver is skipped entirely for a Text-typed Staff).

# Notion property type -> best-fit MyCase custom field type, used only when
# auto-creating a MyCase custom field for a brand-new, unmapped Notion
# column. Types with no sane MyCase equivalent (relation, formula, rollup,
# files, people, etc.) are deliberately left out - skipped with a warning
# rather than silently mis-mapped.
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
