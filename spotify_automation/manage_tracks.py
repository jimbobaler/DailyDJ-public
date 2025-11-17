import sqlite3
from datetime import date
import sys

DB_PATH = "track_history.db"

def add_track(track_id, artist, title, source="", energy_tag=""):
    today = str(date.today())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tracks (track_id, artist, title, last_played, source, energy_tag) VALUES (?, ?, ?, ?, ?, ?)",
            (track_id, artist, title, today, source, energy_tag),
        )
    print(f"Added {artist} – {title}")

def show_tracks(limit=10):
    with sqlite3.connect(DB_PATH) as conn:
        for row in conn.execute("SELECT artist, title, last_played FROM tracks ORDER BY last_played DESC LIMIT ?", (limit,)):
            print(f"{row[0]} – {row[1]} ({row[2]})")

if len(sys.argv) == 1:
    show_tracks()
elif sys.argv[1] == "add" and len(sys.argv) >= 4:
    _, _, artist, title, track_id, *rest = sys.argv
    source = rest[0] if len(rest) > 0 else ""
    tag = rest[1] if len(rest) > 1 else ""
    add_track(track_id, artist, title, source, tag)
else:
    print("Usage:")
    print("  python3 manage_tracks.py                # show recent tracks")
    print("  python3 manage_tracks.py add \"Artist\" \"Title\" track_id [source] [tag]")
