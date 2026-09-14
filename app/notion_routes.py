"""
A small endpoint to confirm the Notion side is wired up correctly after
deployment - hit it in a browser or with curl once NOTION_TOKEN and
NOTION_DATABASE_ID are set, to confirm the integration token can actually
reach the tracked database before wiring up the full sync schedule.
"""
import httpx
from fastapi import APIRouter, HTTPException

from app import notion_client

router = APIRouter(prefix="/notion", tags=["notion"])


@router.get("/status")
def status():
    """Returns the tracked database's property names/types if the Notion
    integration token is valid and has access to it, or a clear error
    otherwise (bad token, or the database hasn't been shared with the
    integration yet)."""
    try:
        schema = notion_client.get_database_schema()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise HTTPException(502, "Notion rejected the token - check NOTION_TOKEN.")
        if exc.response.status_code == 404:
            raise HTTPException(
                502,
                "Notion database not found or not shared with this integration - "
                "check NOTION_DATABASE_ID and that the database is shared with your integration.",
            )
        raise HTTPException(502, f"Notion API error: {exc.response.text}")

    return {"connected": True, "properties": schema}
