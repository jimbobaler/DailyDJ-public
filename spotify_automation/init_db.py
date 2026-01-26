import sqlite3
from pathlib import Path

from spotify_automation import paths

DB_PATH = paths.db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

schema = """
CREATE TABLE IF NOT EXISTS tracks (
    track_id TEXT PRIMARY KEY,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    last_played DATE,
    source TEXT,
    energy_tag TEXT,
    duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS bans (
    track_id TEXT PRIMARY KEY,
    artist TEXT,
    title TEXT,
    reason TEXT,
    banned_at DATE
);

CREATE TABLE IF NOT EXISTS track_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    noted_at DATE NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS playlist_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_label TEXT,
    run_at DATE NOT NULL,
    energy_tag TEXT
);

CREATE TABLE IF NOT EXISTS playlist_run_tracks (
    run_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    track_id TEXT NOT NULL,
    source TEXT,
    gpt_reason TEXT,
    gpt_confidence REAL,
    FOREIGN KEY(run_id) REFERENCES playlist_runs(id)
);
"""

with sqlite3.connect(DB_PATH) as conn:
    conn.executescript(schema)

print(f"Database initialised at {DB_PATH}")
