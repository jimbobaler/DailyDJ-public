import sqlite3

DB_PATH = "track_history.db"

schema = """
CREATE TABLE IF NOT EXISTS tracks (
    track_id TEXT PRIMARY KEY,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    last_played DATE,
    source TEXT,
    energy_tag TEXT
);
"""

with sqlite3.connect(DB_PATH) as conn:
    conn.executescript(schema)

print(f"Database initialised at {DB_PATH}")
