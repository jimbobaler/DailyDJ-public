"""
Lightweight migration helper to normalize the database schema.

It will:
- move the DB to the repo root if it only exists under spotify_automation/
- ensure tables/columns needed for bans, feedback, playlist runs, and durations
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DB = BASE_DIR.parent / "track_history.db"
LEGACY_DB = BASE_DIR / "track_history.db"


def ensure_db_location() -> Path:
    """
    Move legacy DB into the repo root if needed.
    """
    if ROOT_DB.exists():
        return ROOT_DB
    if LEGACY_DB.exists():
        ROOT_DB.write_bytes(LEGACY_DB.read_bytes())
        print(f"Copied legacy DB from {LEGACY_DB} -> {ROOT_DB}")
        return ROOT_DB
    ROOT_DB.touch()
    print(f"Created new DB at {ROOT_DB}")
    return ROOT_DB


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def migrate() -> None:
    db_path = ensure_db_location()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracks (
                track_id TEXT PRIMARY KEY,
                artist TEXT NOT NULL,
                title TEXT NOT NULL,
                last_played DATE,
                source TEXT,
                energy_tag TEXT,
                duration_ms INTEGER
            )
            """
        )

        if not column_exists(conn, "tracks", "duration_ms"):
            conn.execute("ALTER TABLE tracks ADD COLUMN duration_ms INTEGER")
            print("Added duration_ms to tracks")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bans (
                track_id TEXT PRIMARY KEY,
                artist TEXT,
                title TEXT,
                reason TEXT,
                banned_at DATE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS track_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id TEXT NOT NULL,
                verdict TEXT NOT NULL,
                noted_at DATE NOT NULL,
                note TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS playlist_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_label TEXT,
                run_at DATE NOT NULL,
                energy_tag TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS playlist_run_tracks (
                run_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                track_id TEXT NOT NULL,
                source TEXT,
                gpt_reason TEXT,
                gpt_confidence REAL,
                FOREIGN KEY(run_id) REFERENCES playlist_runs(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artist_bans (
                artist TEXT PRIMARY KEY,
                reason TEXT,
                banned_at DATE
            )
            """
        )
        conn.commit()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
