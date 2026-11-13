"""Accept first-party provider outcomes and expose rolling aggregate counts."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import time
from contextlib import closing
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from monitor_auth import monitor_api_token, require_monitor_read_auth

router = APIRouter()
logger = logging.getLogger(__name__)
WINDOW_S = 24 * 60 * 60
RETENTION_S = 2 * WINDOW_S
MAX_BODY = 512
OPERATIONS = {
    "laso": (("argus", "card_quote"), ("argus", "card_issue"), ("argus", "card_checkout")),
    "coinmarketcap": (("argus", "quotes"),),
    "tavily": (("argus", "search"), ("metis", "search")),
}
STATUSES = ("succeeded", "failed", "attempted")
FIELDS = {"event_id", "provider", "source", "operation", "status"}


def _scoped_token() -> str:
    token_file = os.getenv("ALIEN_PROVIDER_EVENTS_TOKEN_FILE", "").strip()
    if token_file:
        try:
            with open(token_file, encoding="utf-8") as stream:
                token = stream.read(257).strip()
            return token if len(token) <= 256 else ""
        except (OSError, UnicodeError):
            return ""
    return os.getenv("ALIEN_PROVIDER_EVENTS_TOKEN", "").strip()


def _require_service_token(request: Request) -> None:
    tokens = (_scoped_token(), monitor_api_token())
    if not any(tokens):
        raise HTTPException(503, "Provider event authentication is not configured")
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token or not any(
        expected and secrets.compare_digest(token.encode(), expected.encode())
        for expected in tokens
    ):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})


def _event(payload: object) -> tuple[str, str, str, str, str]:
    error = HTTPException(422, "Invalid provider event")
    if not isinstance(payload, dict) or payload.keys() != FIELDS:
        raise error
    event_id, provider, source, operation, status = (payload[key] for key in (
        "event_id", "provider", "source", "operation", "status",
    ))
    if not all(isinstance(value, str) for value in (event_id, provider, source, operation, status)):
        raise error
    try:
        identifier = UUID(event_id)
    except ValueError:
        raise error from None
    if (identifier.version != 4 or len(event_id) != 36 or status not in STATUSES
            or (source, operation) not in OPERATIONS.get(provider, ())):
        raise error
    return str(identifier), provider, source, operation, status


def _connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=3)
    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS provider_events (
                event_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                source TEXT NOT NULL,
                operation TEXT NOT NULL,
                status TEXT NOT NULL,
                received_at INTEGER NOT NULL
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS provider_events_received_at ON provider_events (received_at)
        """)
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def _record(path: str, event: tuple[str, str, str, str, str]) -> bool:
    now = int(time.time())
    with closing(_connect(path)) as connection, connection:
        connection.execute("DELETE FROM provider_events WHERE received_at < ?", (now - RETENTION_S,))
        cursor = connection.execute("""
            INSERT INTO provider_events VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO NOTHING
        """, (*event, now))
        if cursor.rowcount == 1:
            return True
        stored = connection.execute("""
            SELECT provider, source, operation, status FROM provider_events WHERE event_id = ?
        """, (event[0],)).fetchone()
        if stored != event[1:]:
            raise HTTPException(409, "Provider event ID already used")
        return False


def _summary(path: str) -> dict:
    now = int(time.time())
    with closing(_connect(path)) as connection, connection:
        # Purge old rows even when all publishers have been quiet.
        oldest = connection.execute("SELECT MIN(received_at) FROM provider_events").fetchone()[0]
        if oldest is not None and oldest < now - RETENTION_S:
            connection.execute("DELETE FROM provider_events WHERE received_at < ?", (now - RETENTION_S,))
        rows = connection.execute("""
            SELECT provider, source, operation, status, COUNT(*)
            FROM provider_events WHERE received_at > ?
            GROUP BY provider, source, operation, status
        """, (now - WINDOW_S,)).fetchall()
    counts = {(provider, source, operation, status): count
              for provider, source, operation, status, count in rows}
    return {
        "state": "ok",
        "window_seconds": WINDOW_S,
        "providers": [
            {"id": provider, "operations": [
                {"source": source, "operation": operation, **{
                    status: counts.get((provider, source, operation, status), 0) for status in STATUSES
                }}
                for source, operation in operations
            ]}
            for provider, operations in OPERATIONS.items()
        ],
    }


@router.post("/api/provider-events", dependencies=[Depends(_require_service_token)])
async def ingest_provider_event(request: Request):
    path = os.getenv("ALIEN_PROVIDER_EVENTS_DB", "").strip()
    if not path:
        raise HTTPException(503, "Provider event storage is not configured")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Expected application/json")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            raise HTTPException(413, "Provider event is too large")
        body.extend(chunk)
    try:
        event = _event(json.loads(body))
    except (ValueError, RecursionError):
        raise HTTPException(422, "Invalid provider event") from None
    try:
        accepted = await run_in_threadpool(_record, path, event)
    except sqlite3.Error:
        logger.warning("Provider event could not be recorded")
        raise HTTPException(503, "Provider event storage is unavailable") from None
    return {"ok": True, "duplicate": not accepted}


@router.get("/api/provider-events", dependencies=[Depends(require_monitor_read_auth)])
async def provider_event_summary():
    path = os.getenv("ALIEN_PROVIDER_EVENTS_DB", "").strip()
    if not path:
        return {"state": "disabled"}
    try:
        return await run_in_threadpool(_summary, path)
    except sqlite3.Error:
        logger.warning("Provider event summary could not be read")
        raise HTTPException(503, "Provider event storage is unavailable") from None
