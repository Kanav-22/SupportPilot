from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY,
    text            TEXT NOT NULL,
    true_category   TEXT NOT NULL,
    true_priority   TEXT,
    source          TEXT,
    status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processed'))
);

CREATE TABLE IF NOT EXISTS triage_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id           INTEGER NOT NULL,
    variant             TEXT NOT NULL CHECK (variant IN ('zero_shot', 'few_shot')),
    provider            TEXT,
    model               TEXT,
    pred_category       TEXT,
    pred_priority       TEXT,
    pred_sentiment      TEXT,
    draft_response      TEXT,
    confidence          REAL,
    escalated           INTEGER DEFAULT 0 CHECK (escalated IN (0, 1)),
    latency_ms          INTEGER,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_results_ticket_variant ON triage_results(ticket_id, variant, provider, model);
"""


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def setup_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        ensure_column(conn, "triage_results", "provider", "TEXT")
        ensure_column(conn, "triage_results", "model", "TEXT")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the SupportPilot SQLite schema.")
    parser.add_argument("--db", default="db/supportpilot.db", help="Path to SQLite database.")
    args = parser.parse_args()

    setup_db(Path(args.db))
    print(f"Created schema at {args.db}")


if __name__ == "__main__":
    main()
