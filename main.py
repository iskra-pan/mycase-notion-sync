import logging

from dotenv import load_dotenv

load_dotenv()  # local dev only; on Cloud Run these come from env vars / Secret Manager

from fastapi import FastAPI

from app.mycase_auth import router as mycase_auth_router
from app.notion_routes import router as notion_router
from app.sync_routes import router as sync_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="MyCase <-> Notion Sync")
app.include_router(mycase_auth_router)
app.include_router(notion_router)
app.include_router(sync_router)


@app.get("/")
def root():
    return {"service": "mycase-notion-sync", "status": "ok"}


@app.get("/health")
def health():
    # Cloud Run readiness/liveness check target.
    return {"status": "ok"}
