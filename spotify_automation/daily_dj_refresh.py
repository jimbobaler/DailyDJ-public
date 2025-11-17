# daily_dj_refresh.py
import random
import sqlite3
from datetime import date, timedelta
import spotipy
from spotipy.oauth2 import SpotifyOAuth

DB_PATH = "track_history.db"
PLAYLIST_ID = "1rDydhUJnGuHZ2x472nQuW"
RECENT_DAYS = 30
TRACKS_PER_DAY = 30

SCOPE = "playlist-modify-private playlist-read-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))

# --- Config rules ---
BANNED_ARTISTS = {
    "the killers",
    "florence and the machine",
    "the 1975",
    "bloc party",
    "twenty one pilots",
}

REDUCE_FREQUENCY = {
    "arctic monkeys",
    "the fratellis",
}

ENERGY_LABELS = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}

# --- Helpers ---
def get_recent_track_ids(days=30):
    cutoff = date.today() - timedelta(days=days)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT track_id FROM tracks WHERE last_played >= ?", (str(cutoff),)
        ).fetchall()
    return {r[0] for r in rows}

def get_candidate_tracks(tag):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT track_id, artist, title FROM tracks WHERE energy_tag=? OR energy_tag IS NULL",
            (tag,),
        ).fetchall()
    return rows

def mark_tracks_played(track_ids):
    today = str(date.today())
    with sqlite3.connect(DB_PATH) as conn:
        for tid in track_ids:
            conn.execute("UPDATE tracks SET last_played=? WHERE track_id=?", (today, tid))
        conn.commit()

# --- Select today's tracks ---
today_index = date.today().weekday()
energy_tag = ENERGY_LABELS[today_index]
print(f"\n🎧 Building playlist for {energy_tag.capitalize()}...")

recent = get_recent_track_ids(RECENT_DAYS)
candidates = get_candidate_tracks(energy_tag)

eligible = []
for tid, artist, title in candidates:
    a_low = artist.lower()
    if not tid or tid in recent:
        continue
    if any(b in a_low for b in BANNED_ARTISTS):
        continue
    if any(r in a_low for r in REDUCE_FREQUENCY) and random.random() < 0.66:
        continue
    eligible.append((tid, artist, title))

if not eligible:
    raise RuntimeError("No eligible tracks found — check DB or filters.")

random.shuffle(eligible)
selected = eligible[:TRACKS_PER_DAY]
track_ids = [t[0] for t in selected]

sp.playlist_replace_items(PLAYLIST_ID, track_ids)
mark_tracks_played(track_ids)

print(f"✅ My Daily DJ refreshed for {energy_tag.capitalize()}")
print(f"Added {len(track_ids)} new tracks:\n")
for _, artist, title in selected[:10]:
    print(f" • {artist} – {title}")

