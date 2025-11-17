import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPE = "playlist-modify-private playlist-read-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))

PLAYLIST_NAME = "My Daily DJ"
USER_ID = sp.current_user()["id"]

# find the playlist
playlists = sp.current_user_playlists(limit=50)["items"]
pl = next((p for p in playlists if p["name"] == PLAYLIST_NAME), None)
if not pl:
    raise Exception("Playlist not found. Run create_my_daily_dj.py first!")

# example: add one track by ID
track_ids = [
    "3PRoXYsngSwjEQWR5PsHWR"  # Everlong – Foo Fighters
]

sp.playlist_replace_items(pl["id"], track_ids)
print(f"Updated '{pl['name']}' with {len(track_ids)} track(s).")
