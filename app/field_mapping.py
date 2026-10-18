"""
Declarative Notion <-> MyCase field mapping, matched to the firm's real
"Case Tracking" database (confirmed live via /notion/status, 2026-10-07)
and the firm's own MyCase field inventory.

Edit THIS file (not the sync engine) whenever the firm wants to add or
remove a synced field - nothing syncs unless it has a row here.

Notion is the source of truth for every field except 6: Contacts, Office,
Lead attorney, Originating attorney, Staff, and Created. Those 6 stay
MyCase-sourced because they aren't plain writable values - 5 are derived
from relational MyCase data with no reverse (Notion -> MyCase) mapping
built yet (Office specifically isn't writable via this API at all,
regardless of source_of_truth), and Created is MyCase's own case-creation
timestamp. For everything else: editing it in Notion overwrites MyCase on
the next sync; editing it in MyCase gets overwritten back by Notion's
value on the next sync. Change source_of_truth per-field if a different
mix is wanted later.

`mycase_field` values for STANDARD_FIELDS are confirmed real MyCase Case
API keys (2026-10-17, against the firm's live docs) - see
mycase_client.py for the confirmed request/response shapes. `mycase_field`
values for CUSTOM_FIELDS are resolved by name via
mycase_client.resolve_custom_field_id() - still assumes the firm named
the MyCase custom field the same as the Notion column; worth a spot-check.
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
    # Non-empty for fields that AREN'T a simple `case[mycase_field]` lookup -
    # these are derived from nested/relational data (clients[], staff[],
    # office{}) and need special-case logic in sync_engine.py. See the
    # DERIVED_FIELD_NOTES block below for what each value means.
    derived: str = ""


# =====================================================================
# Case Overview and Case Information  ->  MyCase's built-in case fields
# =====================================================================
# Keys below are confirmed real (2026-10-17, live docs) for the ones with
# a plain `mycase_field` - POST/PUT /cases: name, case_number, opened_date,
# closed_date, practice_area, case_stage, description, sol_date, status.
#
# "Conflict Check"/"Conflict Check Notes" are NOT in MyCase's confirmed
# standard Case schema - moved to CUSTOM_FIELDS below (they must be
# MyCase custom fields, which also matches the firm's own uncertainty
# about their type).
STANDARD_FIELDS: list[FieldMapping] = [
    FieldMapping("Name", "name", FieldKind.STANDARD, "title", SourceOfTruth.NOTION,
                 "Use the complete MyCase case name. Do not substitute only the beneficiary's name."),
    FieldMapping("Case Number", "case_number", FieldKind.STANDARD, "rich_text", SourceOfTruth.NOTION,
                 "Preserve the exact value, including leading zeros."),
    FieldMapping("Date Opened", "opened_date", FieldKind.STANDARD, "date", SourceOfTruth.NOTION,
                 "Copy the source date without timezone-related day shifts."),
    FieldMapping("Date Closed", "closed_date", FieldKind.STANDARD, "date", SourceOfTruth.NOTION,
                 "Leave blank when no date exists."),
    FieldMapping("Practice Area", "practice_area", FieldKind.STANDARD, "rich_text", SourceOfTruth.NOTION,
                 "Must match a practice area name already configured in MyCase - a non-matching value defaults to blank."),
    FieldMapping("Case Stage", "case_stage", FieldKind.STANDARD, "select", SourceOfTruth.NOTION,
                 "Must match a stage name already configured in MyCase - a non-matching value defaults to blank."),
    FieldMapping("Description", "description", FieldKind.STANDARD, "rich_text", SourceOfTruth.NOTION,
                 "Preserve line breaks and supported formatting."),

    # --- Derived fields: NOT a simple case[key] lookup, see sync_engine.py ---
    FieldMapping("Contacts", "clients", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Display all linked MyCase contact names. Never create/replace contacts by name alone.",
                 derived="clients_display"),
    FieldMapping("Office", "office", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Confirmed read-only via this API - office isn't a settable field on case create/update.",
                 derived="office_name"),
    FieldMapping("Lead attorney", "staff", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Display only - derived from staff[].lead_lawyer, resolved to a name via "
                 "mycase_client.get_staff_directory (GET /v1/staff).",
                 derived="staff_lead_attorney"),
    FieldMapping("Originating attorney", "staff", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "Display only - derived from staff[].originating_lawyer, same dependency as Lead attorney.",
                 derived="staff_originating_attorney"),
    # Real Notion "people" property - resolved MyCase staff ID -> email
    # (via the staff directory) -> Notion user ID (via notion_users.py),
    # never guessed from a name. Any staff member that can't be resolved
    # at either step is skipped and logged, not written incorrectly.
    FieldMapping("Staff", "staff", FieldKind.STANDARD, "people", SourceOfTruth.MYCASE,
                 "Multiple staff members supported. Matched to Notion users by email only.",
                 derived="staff_people"),
    FieldMapping("Created", "created_at", FieldKind.STANDARD, "rich_text", SourceOfTruth.MYCASE,
                 "MyCase's case creation timestamp - the confirmed schema has no separate 'creator' person field."),
]

# =====================================================================
# Custom Fields  ->  MyCase custom_field_values
# =====================================================================
CUSTOM_FIELDS: list[FieldMapping] = [
    # Not in MyCase's confirmed standard Case schema - must be custom
    # fields (also matches the firm's own uncertainty about their type).
    FieldMapping("Conflict Check", "Conflict Check", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Confirm MyCase's real field_type (text/select/checkbox) once visible in GET /custom_fields."),
    FieldMapping("Conflict Check Notes", "Conflict Check Notes", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Preserve line breaks."),
    FieldMapping("Email", "Email", FieldKind.CUSTOM, "email", SourceOfTruth.NOTION,
                 "The case-level custom Email field, not a contact's email."),
    FieldMapping("Phone", "Phone", FieldKind.CUSTOM, "phone_number", SourceOfTruth.NOTION,
                 "Preserve country code, extension, and exact source formatting."),
    FieldMapping("Date Added", "Date Added", FieldKind.CUSTOM, "date", SourceOfTruth.NOTION,
                 "Keep separate from Date Opened and Created."),
    FieldMapping("Lead Type", "Lead Type", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Open question: confirm source type and full option list if it's a dropdown."),
    FieldMapping("Lead Source", "Lead Source", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Open question: confirm dropdown options if applicable."),
    FieldMapping("Case Type", "Case Type", FieldKind.CUSTOM, "select", SourceOfTruth.NOTION,
                 "Notion's current Select options are not a verified complete list of MyCase's options."),
    FieldMapping("G-Drive link", "G-Drive link", FieldKind.CUSTOM, "url", SourceOfTruth.NOTION,
                 "Likely superseded once the separate Google Drive folder automation is built."),
    FieldMapping("USCIS Receipt Number - 1", "USCIS Receipt Number - 1", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Keep separate from receipt number 2."),
    FieldMapping("USCIS Receipt Number - 2", "USCIS Receipt Number - 2", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Keep separate from receipt number 1."),

    # Filing/expense slots 1-4. NOTE: slot 2's "Type of Filing" has a
    # capital F (unlike slots 1/3/4's "Type of filing") - this is the
    # firm's real property name, not a typo - preserved exactly.
    FieldMapping("1 Filing — Type of filing", "1 Filing — Type of filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION, ""),
    FieldMapping("1 Filing — Date", "1 Filing — Date", FieldKind.CUSTOM, "date", SourceOfTruth.NOTION, ""),
    FieldMapping("1 Filing — Card", "1 Filing — Card", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Card label/reference only - never full card numbers or security codes."),
    FieldMapping("1 Filing — Amount", "1 Filing — Amount", FieldKind.CUSTOM, "number", SourceOfTruth.NOTION,
                 "Open question: confirm currency and decimal precision."),

    FieldMapping("2 Filing — Type of Filing", "2 Filing — Type of Filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION, ""),
    FieldMapping("2 Filing — Date", "2 Filing — Date", FieldKind.CUSTOM, "date", SourceOfTruth.NOTION, ""),
    FieldMapping("2 Filing — Amount", "2 Filing — Amount", FieldKind.CUSTOM, "number", SourceOfTruth.NOTION, ""),
    FieldMapping("2 Filing — Card", "2 Filing — Card", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Card label/reference only."),

    FieldMapping("3 Filing/Expenses — Type of filing", "3 Filing/Expenses — Type of filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION, ""),
    FieldMapping("3 Filing/Expenses — Date", "3 Filing/Expenses — Date", FieldKind.CUSTOM, "date", SourceOfTruth.NOTION, ""),
    FieldMapping("3 Filing/Expenses — Amount", "3 Filing/Expenses — Amount", FieldKind.CUSTOM, "number", SourceOfTruth.NOTION, ""),
    FieldMapping("3 Filing/Expenses — Card", "3 Filing/Expenses — Card", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Card label/reference only."),

    FieldMapping("4 Filing/Expenses — Type of filing", "4 Filing/Expenses — Type of filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION, ""),
    FieldMapping("4 Filing/Expenses — Date", "4 Filing/Expenses — Date", FieldKind.CUSTOM, "date", SourceOfTruth.NOTION, ""),
    FieldMapping("4 Filing/Expenses — Amount", "4 Filing/Expenses — Amount", FieldKind.CUSTOM, "number", SourceOfTruth.NOTION, ""),
    FieldMapping("4 Filing/Expenses — Card", "4 Filing/Expenses — Card", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Card label/reference only."),

    FieldMapping("Filing notes", "Filing notes", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION, ""),
    FieldMapping("Billing transferred", "Billing transferred", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Open question: confirm whether the MyCase source is actually a checkbox/date/dropdown/text."),
    FieldMapping("Payment arrangements if any:", "Payment arrangements if any:", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Exact property name includes the trailing colon."),
    FieldMapping("Date — Requested to Close", "Date — Requested to Close", FieldKind.CUSTOM, "date", SourceOfTruth.NOTION,
                 "A closure *request* date - keep separate from the actual Date Closed."),
    FieldMapping("Payment status for filing", "Payment status for filing", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Open question: confirm dropdown options if applicable."),
    # Unlike Lead/Originating attorney (confirmed relational - boolean
    # flags on the staff[] array), "Case Manager" is a genuine MyCase
    # custom field, so a plain text write-back works normally - no ID
    # resolution needed here, assuming MyCase's field_type for it is a
    # plain text type and not some staff-reference type (worth a glance
    # at GET /custom_fields to confirm).
    FieldMapping("Case Manager", "Case Manager", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Display the MyCase case manager's name; confirm the field_type in GET /custom_fields."),
    # OPEN QUESTION: MyCase's confirmed built-in `status` field is only
    # ever "open" or "closed" - if the firm's "Main Status" needs more
    # options than that (their own note implies it does), it's genuinely
    # a separate custom field, as mapped here. If it turns out "Main
    # Status" actually means the built-in open/closed status, this
    # should move to STANDARD_FIELDS as mycase_field="status" instead.
    FieldMapping("Main Status", "Main Status", FieldKind.CUSTOM, "rich_text", SourceOfTruth.NOTION,
                 "Separate concept from Case Stage. Open question: confirm against MyCase's built-in open/closed status."),
]

ALL_FIELDS: list[FieldMapping] = STANDARD_FIELDS + CUSTOM_FIELDS

# "MyCase Link" is NOT one of MyCase's own fields being mirrored - it's
# generated by this app after matching/creating a matter, and written back
# to Notion. Normally read-only from the sync's perspective.
MATTER_ID_PROPERTY = "MyCase Link"
MATTER_ID_PROPERTY_TYPE = "url"

# --- Nothing currently excluded ---
#
# "Staff" / "Lead attorney" / "Originating attorney" are fully wired up
# (see the `derived=` fields above, sync_engine.py, and
# mycase_client.get_staff_directory / notion_users.py) - a case's staff[]
# array gives IDs, GET /v1/staff resolves each to a name + email, and
# notion_users.py matches that email to a Notion workspace user. Anyone
# who fails any step (no directory entry, no email, no Notion account) is
# skipped and logged, never guessed.

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
