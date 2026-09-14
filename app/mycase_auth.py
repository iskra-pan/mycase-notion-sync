"""
MyCase OAuth 2.0 (Authorization Code grant), per:
https://mycaseapi.stoplight.io/docs/mycase-api-documentation

Flow:
  1. GET /auth/mycase/login     -> redirect the firm's MyCase admin to MyCase
  2. MyCase redirects back to  -> GET /auth/mycase/callback?code=...&state=...
  3. We exchange the code for an access_token + refresh_token and store them.

  Access tokens last 24h, refresh tokens last 2 weeks, so a refresh
  MUST happen on a schedule (see /internal/refresh-mycase-token) or the
  connection goes stale if nothing calls the API for two weeks straight.
"""
import logging
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings
from app.security import new_state, verify_state
from app.storage import load_mycase_tokens, save_mycase_tokens

logger = logging.getLogger("mycase_auth")
router = APIRouter(prefix="/auth/mycase", tags=["mycase-auth"])

TOKEN_URL = f"{settings.mycase_auth_base}/tokens"
AUTHORIZE_URL = f"{settings.mycase_auth_base}/login_sessions/new"


@router.get("/login")
def login():
    """Send the firm's MyCase admin here once to authorize this app."""
    params = {
        "client_id": settings.mycase_client_id,
        "redirect_uri": settings.mycase_redirect_uri,
        "response_type": "code",
        "state": new_state(),
    }
    return RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/callback")
def callback(request: Request):
    """
    This is the endpoint whose full URL you give MyCase as the
    'redirect URI' during onboarding, e.g.:
        https://<your-cloud-run-url>/auth/mycase/callback
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        raise HTTPException(400, f"MyCase authorization denied: {error}")
    if not code or not state or not verify_state(state):
        raise HTTPException(400, "Missing or invalid/expired state - please restart at /auth/mycase/login")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": settings.mycase_client_id,
            "client_secret": settings.mycase_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.mycase_redirect_uri,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error("MyCase token exchange failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(502, f"MyCase token exchange failed: {resp.text}")

    payload = resp.json()
    save_mycase_tokens(
        access_token=payload["access_token"],
        refresh_token=payload["refresh_token"],
        expires_in=payload.get("expires_in", 24 * 3600),
    )
    logger.info("MyCase connected successfully.")
    return HTMLResponse("<h3>MyCase connected successfully.</h3><p>You can close this window.</p>")


@router.get("/status")
def status():
    tokens = load_mycase_tokens()
    if not tokens:
        return {"connected": False}
    return {
        "connected": True,
        "expires_in_seconds": max(0, int(tokens["expires_at"] - time.time())),
    }


def refresh_mycase_token() -> dict:
    tokens = load_mycase_tokens()
    if not tokens:
        raise HTTPException(400, "No MyCase connection on file yet - visit /auth/mycase/login first.")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": settings.mycase_client_id,
            "client_secret": settings.mycase_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error("MyCase token refresh failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(502, f"MyCase token refresh failed: {resp.text}")

    payload = resp.json()
    save_mycase_tokens(
        access_token=payload["access_token"],
        # MyCase, like most OAuth servers, may rotate the refresh token -
        # always persist whatever comes back, falling back to the old one.
        refresh_token=payload.get("refresh_token", tokens["refresh_token"]),
        expires_in=payload.get("expires_in", 24 * 3600),
    )
    logger.info("MyCase token refreshed.")
    return {"refreshed": True}


@router.post("/internal/refresh")
def internal_refresh(x_task_secret: str = Header(default="")):
    """
    Call this on a schedule (Cloud Scheduler, every 12h) to keep the
    connection alive indefinitely. Protected by a shared secret header
    so it can't be triggered by random internet traffic.
    """
    if x_task_secret != settings.internal_task_secret:
        raise HTTPException(403, "Forbidden")
    return refresh_mycase_token()


def get_valid_access_token() -> str:
    """Used by the future sync logic - returns a live access token, refreshing first if it's about to expire."""
    tokens = load_mycase_tokens()
    if not tokens:
        raise HTTPException(400, "MyCase is not connected yet - visit /auth/mycase/login first.")
    if tokens["expires_at"] - time.time() < 300:  # refresh 5 min before expiry
        refresh_mycase_token()
        tokens = load_mycase_tokens()
    return tokens["access_token"]
