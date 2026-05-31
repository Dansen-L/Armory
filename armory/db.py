"""Armory database layer — SQLite via stdlib sqlite3."""

import contextlib
import os
import sqlite3
from pathlib import Path
from typing import Iterator


def get_db_path() -> Path:
    """Return the SQLite DB path, respecting ARMORY_DB_PATH env var."""
    env_path = os.environ.get("ARMORY_DB_PATH")
    if env_path:
        return Path(env_path)
    db_dir = Path.home() / ".armory"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "armory.db"


@contextlib.contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Context manager that yields a sqlite3 connection and closes it on exit.

    Usage::
        with db.get_connection() as conn:
            rows = conn.execute("SELECT ...").fetchall()
    # Connection is closed here — file descriptor released.
    """
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


CREATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_payloads (
    id TEXT PRIMARY KEY,
    class_slug TEXT NOT NULL,
    group_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    payload_string TEXT NOT NULL,
    how_it_works TEXT NOT NULL,
    prerequisites_json TEXT DEFAULT '[]',
    waf_bypass_notes TEXT DEFAULT '',
    severity_context TEXT DEFAULT '',
    cve_refs_json TEXT DEFAULT '[]',
    tags_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_groups (
    id TEXT PRIMARY KEY,
    class_slug TEXT NOT NULL,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    difficulty TEXT DEFAULT 'medium',
    prerequisites_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_classes (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    owasp TEXT DEFAULT '',
    severity_range_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_id TEXT NOT NULL,
    class_slug TEXT NOT NULL,
    group_slug TEXT NOT NULL,
    label TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_id TEXT NOT NULL,
    note_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_id TEXT NOT NULL,
    class_slug TEXT NOT NULL,
    group_slug TEXT NOT NULL,
    viewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    searched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT UNIQUE NOT NULL,
    prompt_hash TEXT NOT NULL,
    response_text TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db() -> None:
    """Create all tables on first run if they don't exist."""
    with get_connection() as conn:
        conn.executescript(CREATE_SCHEMA)
