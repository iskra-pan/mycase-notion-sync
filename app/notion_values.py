"""
Conversion between Notion's verbose property-value JSON and plain Python
values, keyed by Notion property type. This shape is stable, documented
API surface (https://developers.notion.com/reference/property-value-object)
- unlike the MyCase side, nothing here is a guess.
"""
from typing import Any, Optional


def notion_value_to_plain(notion_type: str, prop: Optional[dict]) -> Any:
    if not prop:
        return None
    if notion_type == "title":
        return "".join(t["plain_text"] for t in prop.get("title", [])) or None
    if notion_type == "rich_text":
        return "".join(t["plain_text"] for t in prop.get("rich_text", [])) or None
    if notion_type == "email":
        return prop.get("email")
    if notion_type == "phone_number":
        return prop.get("phone_number")
    if notion_type == "url":
        return prop.get("url")
    if notion_type == "number":
        return prop.get("number")
    if notion_type == "checkbox":
        return prop.get("checkbox")
    if notion_type == "select":
        sel = prop.get("select")
        return sel["name"] if sel else None
    if notion_type == "status":
        st = prop.get("status")
        return st["name"] if st else None
    if notion_type == "date":
        d = prop.get("date")
        return d["start"] if d else None
    if notion_type == "people":
        return ", ".join(p.get("name", "") for p in prop.get("people", [])) or None
    raise ValueError(f"Unsupported notion_type for read: {notion_type}")


def plain_to_notion_value(notion_type: str, value: Any) -> dict:
    """Returns the value ready to nest under a property name in a
    pages.update `properties` body, e.g. {"Status": plain_to_notion_value(...)}"""
    if notion_type == "title":
        return {"title": [{"text": {"content": str(value or "")}}]}
    if notion_type == "rich_text":
        return {"rich_text": [{"text": {"content": str(value or "")}}]}
    if notion_type == "email":
        return {"email": value or None}
    if notion_type == "phone_number":
        return {"phone_number": value or None}
    if notion_type == "url":
        return {"url": value or None}
    if notion_type == "number":
        return {"number": value}
    if notion_type == "checkbox":
        return {"checkbox": bool(value)}
    if notion_type == "select":
        return {"select": {"name": value} if value else None}
    if notion_type == "status":
        return {"status": {"name": value} if value else None}
    if notion_type == "date":
        return {"date": {"start": value} if value else None}
    if notion_type == "people":
        # Writing "people" back requires Notion user IDs, not names - MyCase
        # attorney/case-manager names would need to be resolved to Notion
        # user IDs first (e.g. a small lookup table by name/email). Left as
        # a follow-up if MyCase -> Notion writes to this field are needed.
        raise ValueError("Writing a 'people' property requires a name -> Notion user ID lookup - not implemented yet")
    raise ValueError(f"Unsupported notion_type for write: {notion_type}")
