"""
Lightweight migration helper to normalize the database schema.

It will:
- move the DB to the repo root if it only exists under spotify_automation/
- ensure tables/columns needed for bans, feedback, playlist runs, and durations
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from spotify_automation import paths


def ensure_db_location() -> Path:
    """
    Prefer DAILYDJ_HOME if set or present; otherwise fall back to legacy path.
    """
    db_path = paths.db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        return db_path
    legacy = Path(__file__).resolve().parent / "track_history.db"
    if not db_path.exists() and legacy.exists() and db_path != legacy:
        db_path.write_bytes(legacy.read_bytes())
        print(f"Copied legacy DB from {legacy} -> {db_path}")
        return db_path
    db_path.touch()
    print(f"Created new DB at {db_path}")
    return db_path


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
