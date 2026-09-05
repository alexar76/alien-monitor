"""Bearer/service-token and signed browser-session guard for Alien Monitor.

Behaviour:
- Service clients authenticate with the configured Bearer token.
- Browsers exchange that token once for a signed HttpOnly session cookie; unsafe
  cookie-authenticated requests additionally require an origin-bound CSRF marker.
- No token AND not production: allowed (local dev / smoke tests).
- No token AND production: **refused** with 503 — refuse to fail open in prod.

Production is detected via ``ALIEN_ENV`` / ``AIFACTORY_ENV`` ∈ {production|prod|live}
or any of ``AIFACTORY_PROD=1`` / ``AIFACTORY_PRODUCTION=1``. This mirrors the same
production-mode detection used by ``services/ai_market_protocol/config.py`` and
``security/prod_startup_guard.py`` — keeping a single source of truth prevents the
classic "looks safe in staging, wide-open in prod" failure mode.
"""

from __future__ import annotations

import logging
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

_PRODUCTION_ENV_TAGS = frozenset({"production", "prod", "live"})
MONITOR_SESSION_COOKIE = "aicom_alien_session"
MONITOR_CSRF_HEADER = "x-alien-csrf"
_SESSION_TTL_SECONDS = 8 * 60 * 60


def monitor_api_token() -> str:
    return (os.environ.get("ALIEN_API_TOKEN") or os.environ.get("ALIEN_MONITOR_API_TOKEN") or "").strip()


def _is_production_env() -> bool:
    for key in ("ALIEN_ENV", "AIFACTORY_ENV"):
        if os.environ.get(key, "").strip().lower() in _PRODUCTION_ENV_TAGS:
            return True
    for key in ("AIFACTORY_PROD", "AIFACTORY_PRODUCTION"):
        if os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


def create_monitor_session() -> str:
    """Create a short-lived signed browser session without exposing the root token."""
    expected = monitor_api_token()
    if not expected:
        raise RuntimeError("ALIEN_API_TOKEN is not configured")
    expires = int(time.time()) + _SESSION_TTL_SECONDS
    nonce = secrets.token_urlsafe(18)
    payload = f"{expires}.{nonce}"
    signature = hmac.new(expected.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def monitor_session_valid(value: str | None) -> bool:
    expected = monitor_api_token()
    raw = (value or "").strip()
    if not expected or not raw:
        return False
    try:
        expires_raw, nonce, signature = raw.split(".", 2)
        expires = int(expires_raw)
    except (TypeError, ValueError):
        return False
    now = int(time.time())
    if expires < now or expires > now + _SESSION_TTL_SECONDS + 60:
        return False
    payload = f"{expires}.{nonce}"
    wanted = hmac.new(expected.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return secrets.compare_digest(signature, wanted)


def monitor_cookie_secure() -> bool:
    """Production cookies are HTTPS-only; local development remains usable over HTTP."""
    return _is_production_env()


def _cookie_csrf_valid(request: Request) -> bool:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return True
    if (request.headers.get(MONITOR_CSRF_HEADER) or "").strip() != "1":
        return False
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    allowed = set(cors_allow_origins())
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").strip()
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",", 1)[0].strip()
    if host:
        allowed.add(f"{proto}://{host}")
    return origin.rstrip("/") in {item.rstrip("/") for item in allowed}


_PROD_NO_TOKEN_WARNED = False


def require_monitor_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    expected = monitor_api_token()
    if not expected:
        if _is_production_env():
            global _PROD_NO_TOKEN_WARNED
            if not _PROD_NO_TOKEN_WARNED:
                logger.error(
                    "ALIEN_API_TOKEN is not set in production — refusing all auth-gated requests. "
                    "Set ALIEN_API_TOKEN (or ALIEN_MONITOR_API_TOKEN) to a unique secret."
                )
                _PROD_NO_TOKEN_WARNED = True
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ALIEN_API_TOKEN not configured; refusing in production",
            )
        # Non-production: allow unauthenticated access for local dev convenience.
        return
    token = (credentials.credentials if credentials else "").strip()
    # Service-to-service clients keep using Bearer. Browsers exchange that root
    # token once for an HttpOnly signed session and never receive it in JS bundles.
    if token and secrets.compare_digest(token, expected):
        return
    if monitor_session_valid(request.cookies.get(MONITOR_SESSION_COOKIE)):
        if not _cookie_csrf_valid(request):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def monitor_public_read_allowed() -> bool:
    """Public demo UI (summary/topology/ws stream) without Bearer token."""
    if not _is_production_env():
        return True
    return os.environ.get("ALIEN_PUBLIC_READ", "").strip().lower() in ("1", "true", "yes", "on")


def require_monitor_read_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Read APIs (summary, topology, Pulse /api/pulse/state): open in dev; in production require token unless ALIEN_PUBLIC_READ=1."""
    if monitor_public_read_allowed():
        return
    require_monitor_auth(request, credentials)


def require_monitor_state_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Heavy /api/state dump — always token-gated in production (even public demo)."""
    if not _is_production_env():
        return
    require_monitor_auth(request, credentials)


def monitor_control_token_valid(token: str | None) -> bool:
    """Validate Bearer token for WebSocket control commands (set_mode, bootstrap)."""
    expected = monitor_api_token()
    if not expected:
        return not _is_production_env()
    got = (token or "").strip()
    return bool(got) and secrets.compare_digest(got, expected)


def monitor_ws_token_valid(token: str | None, session_cookie: str | None = None) -> bool:
    """Validate a WebSocket Authorization header or HttpOnly browser session."""
    return monitor_control_token_valid(token) or monitor_session_valid(session_cookie)


def monitor_websocket_origin_allowed(origin: str | None, host: str | None) -> bool:
    """Reject cross-site browser WebSockets while allowing non-browser clients."""
    raw_origin = (origin or "").strip()
    if not raw_origin:
        return True
    parsed = urlsplit(raw_origin)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    allowed = {item.rstrip("/") for item in cors_allow_origins()}
    raw_host = (host or "").strip()
    if raw_host:
        allowed.add(f"http://{raw_host}")
        allowed.add(f"https://{raw_host}")
    return raw_origin.rstrip("/") in allowed


def cors_allow_origins() -> list[str]:
    raw = (os.environ.get("ALIEN_CORS_ORIGINS") or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://127.0.0.1:9100",
        "http://localhost:9100",
        "http://127.0.0.1:9080",
        "http://localhost:9080",
        "https://magic-ai-factory.com",
        "https://www.magic-ai-factory.com",
        "https://modeldev.modelmarket.dev",
    ]
