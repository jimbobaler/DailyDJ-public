import spotipy
from spotipy.oauth2 import SpotifyOAuth
import sqlite3
from datetime import date
import json
import os

DB_PATH = "track_history.db"
TAG_FILE = "energy_tag_map.json"

def load_tag_map():
    if os.path.exists(TAG_FILE):
        with open(TAG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tag_map(mapping):
    with open(TAG_FILE, "w") as f:
        json.dump(mapping, f, indent=2)

def ask_for_tag(name):
    print(f"\nNo energy tag known for playlist: '{name}'")
    while True:
        tag = input("Enter a weekday tag (monday..sunday) or leave blank to skip: ").strip().lower()
        if tag in ("", "monday","tuesday","wednesday","thursday","friday","saturday","sunday"):
            return tag
        print("❌ Invalid tag. Try again.")

def add_track(conn, track_id, artist, title, source, energy_tag=""):
    conn.execute(
        "INSERT OR IGNORE INTO tracks (track_id, artist, title, last_played, source, energy_tag) VALUES (?, ?, ?, ?, ?, ?)",
        (track_id, artist, title, None, source, energy_tag),
    )

# --- load or create tag map
tag_map = load_tag_map()

# --- Spotify auth
SCOPE = "playlist-read-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))

# --- list playlists
playlists = sp.current_user_playlists(limit=50)["items"]
print("\n=== Your Playlists ===")
for i, pl in enumerate(playlists, 1):
    print(f"{i}. {pl['name']}")
choice = input("\nEnter the number(s) of the playlists to import (comma-separated): ")

selected_indexes = [int(x.strip()) for x in choice.split(",") if x.strip().isdigit()]

with sqlite3.connect(DB_PATH) as conn:
    for idx in selected_indexes:
        pl = playlists[idx - 1]
        pl_name = pl["name"]
        # get or ask for tag
        tag = tag_map.get(pl_name)
        if tag is None:
            tag = ask_for_tag(pl_name)
            if tag:
                tag_map[pl_name] = tag
                save_tag_map(tag_map)
        print(f"\nImporting: {pl_name}  (energy_tag='{tag}')")
        results = sp.playlist_items(pl["id"], additional_types=["track"])
        while results:
            for item in results["items"]:
                track = item.get("track")
                if not track or not track.get("id"):
                    continue
                tid = track["id"]
                artist = ", ".join(a["name"] for a in track["artists"])
                title = track["name"]
                add_track(conn, tid, artist, title, pl_name, tag)
            if results["next"]:
                results = sp.next(results)
            else:
                break
    conn.commit()

print("\n✅ Import complete.")

