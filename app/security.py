"""
Stateless signed `state` tokens for the OAuth CSRF check.

We deliberately avoid a server-side session store here: Cloud Run may
route the /login request and the /callback request to two different
container instances, so anything held only in memory could be lost.
Instead the state value is self-verifying (HMAC-signed, time-limited).
"""
import base64
import hashlib
import hmac
import time

from app.config import settings

_MAX_AGE_SECONDS = 15 * 60  # the OAuth dance must complete within 15 minutes


def _sign(payload: str) -> str:
    return hmac.new(
        settings.internal_task_secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def new_state() -> str:
    ts = str(int(time.time()))
    sig = _sign(ts)
    raw = f"{ts}.{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_state(state: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(state.encode()).decode()
        ts, sig = raw.split(".", 1)
    except Exception:
        return False
    if not hmac.compare_digest(sig, _sign(ts)):
        return False
    return (time.time() - float(ts)) < _MAX_AGE_SECONDS
