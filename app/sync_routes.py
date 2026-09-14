"""
Endpoints for Cloud Scheduler to hit on a timer. Protected the same way as
/auth/mycase/internal/refresh - a shared secret header, not public traffic.
"""
from fastapi import APIRouter, Header, HTTPException

from app import sync_engine
from app.config import settings

router = APIRouter(prefix="/sync", tags=["sync"])


def _check_secret(x_task_secret: str) -> None:
    if x_task_secret != settings.internal_task_secret:
        raise HTTPException(403, "Forbidden")


@router.post("/poll-notion")
def poll_notion(x_task_secret: str = Header(default="")):
    """Notion -> MyCase: new/changed Notion pages create/update matters.
    Suggested schedule: every 5 minutes."""
    _check_secret(x_task_secret)
    return sync_engine.sync_new_and_changed_notion_pages()


@router.post("/poll-mycase")
def poll_mycase(x_task_secret: str = Header(default="")):
    """MyCase -> Notion: changed matters update their Notion page.
    Suggested schedule: every 5-10 minutes."""
    _check_secret(x_task_secret)
    return sync_engine.sync_changed_mycase_matters()


@router.post("/poll-notion-schema")
def poll_notion_schema(x_task_secret: str = Header(default="")):
    """New Notion database columns -> new MyCase custom fields.
    Suggested schedule: hourly (schema changes are rare)."""
    _check_secret(x_task_secret)
    return sync_engine.sync_new_notion_properties_to_mycase()
