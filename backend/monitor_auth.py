"""Optional Bearer token for sensitive Alien Monitor API routes."""

from __future__ import annotations

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def monitor_api_token() -> str:
    return (os.environ.get("ALIEN_API_TOKEN") or os.environ.get("ALIEN_MONITOR_API_TOKEN") or "").strip()


def require_monitor_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    expected = monitor_api_token()
    if not expected:
        return
    token = (credentials.credentials if credentials else "").strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def cors_allow_origins() -> list[str]:
    raw = (os.environ.get("ALIEN_CORS_ORIGINS") or "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://127.0.0.1:9100",
        "http://localhost:9100",
        "http://127.0.0.1:9080",
        "http://localhost:9080",
    ]
