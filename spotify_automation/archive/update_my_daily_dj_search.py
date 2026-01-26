# update_my_daily_dj_search.py
import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPE = "playlist-modify-private playlist-read-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))
PLAYLIST_ID = "1rDydhUJnGuHZ2x472nQuW"

def find_track_id(artist, title, market="GB"):
    q = f'track:"{title}" artist:"{artist}"'
    res = sp.search(q=q, type="track", limit=5, market=market)
    for t in res["tracks"]["items"]:
        artists = [a["name"].lower() for a in t["artists"]]
        if artist.lower() in artists:
            return t["id"], f'{t["name"]} — {", ".join(a["name"] for a in t["artists"])}'
    return None, None

# put the songs you actually want here:
wanted = [
    ("Foo Fighters", "Everlong"),
    ("Weezer", "Buddy Holly"),
    ("Maxïmo Park", "Apply Some Pressure"),
]

track_ids = []
for artist, title in wanted:
    tid, label = find_track_id(artist, title)
    if tid:
        print("✓", label)
        track_ids.append(tid)
    else:
        print("✗ not found:", artist, "-", title)

sp.playlist_replace_items(PLAYLIST_ID, track_ids)
print(f"\nUpdated My Daily DJ with {len(track_ids)} track(s).")
