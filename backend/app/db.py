"""SQLite veri katmanı. Harici veritabanı gerekmez; her şey tek dosyada."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .config import DB_PATH

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS connections (
    connector_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    secrets TEXT,
    status TEXT DEFAULT 'unknown',
    status_message TEXT,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    icon TEXT,
    color TEXT,
    system_prompt TEXT,
    model TEXT,
    effort TEXT,
    connectors TEXT,          -- JSON listesi
    auto_approve INTEGER NOT NULL DEFAULT 0,
    created_at REAL,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    agent_id TEXT,
    title TEXT,
    status TEXT,              -- idle | running | awaiting_approval | error
    error TEXT,
    api_messages TEXT,        -- Claude API'ye gönderilen tam mesaj geçmişi (JSON)
    pending TEXT,             -- onay bekleyen araç çağrıları (JSON)
    source TEXT,              -- chat | automation
    usage_in INTEGER DEFAULT 0,
    usage_out INTEGER DEFAULT 0,
    created_at REAL,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    kind TEXT,                -- user | assistant | tool_call | tool_result | approval | error | system
    payload TEXT,
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_events_conv ON events(conversation_id, id);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    agent_id TEXT,
    connector_id TEXT,
    tool TEXT,
    input TEXT,
    result TEXT,
    ok INTEGER,
    duration_ms INTEGER,
    approved_by TEXT,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS automations (
    id TEXT PRIMARY KEY,
    name TEXT,
    agent_id TEXT,
    prompt TEXT,
    interval_minutes INTEGER,
    enabled INTEGER DEFAULT 1,
    last_run REAL,
    last_conversation_id TEXT,
    created_at REAL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_conn = _connect()


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    with _lock:
        try:
            yield _conn
            _conn.commit()
        except Exception:
            _conn.rollback()
            raise


def init_db() -> None:
    with tx() as c:
        c.executescript(SCHEMA)


def now() -> float:
    return time.time()


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in _conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list = ()) -> int:
    with tx() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid or 0


# ---- Ayarlar -------------------------------------------------------------

def get_setting(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return default


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


# ---- Olaylar -------------------------------------------------------------

def add_event(conversation_id: str, kind: str, payload: dict[str, Any]) -> None:
    execute(
        "INSERT INTO events(conversation_id, kind, payload, created_at) VALUES(?,?,?,?)",
        (conversation_id, kind, json.dumps(payload, ensure_ascii=False, default=str), now()),
    )


def list_events(conversation_id: str, after_id: int = 0) -> list[dict[str, Any]]:
    rows = query(
        "SELECT * FROM events WHERE conversation_id=? AND id>? ORDER BY id",
        (conversation_id, after_id),
    )
    for r in rows:
        r["payload"] = json.loads(r["payload"])
    return rows
