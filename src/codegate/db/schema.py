from __future__ import annotations

import sqlite3

INIT_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    diff_text TEXT NOT NULL,
    diff_hash TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    capability_token TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    options_json TEXT NOT NULL,
    correct_option_id TEXT NOT NULL,
    explanation TEXT DEFAULT '',
    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_diff_hash ON sessions(diff_hash);
CREATE INDEX IF NOT EXISTS idx_questions_session ON questions(session_id);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize database tables, pragmas, and indexes."""
    conn.executescript(INIT_SCHEMA_SQL)
    conn.commit()
