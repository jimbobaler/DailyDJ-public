import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPE = "playlist-modify-private playlist-read-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))

PLAYLIST_ID = "1rDydhUJnGuHZ2x472nQuW"

# Replace this list with whatever you want to test
track_ids = [
    "3PRoXYsngSwjEQWR5PsHWR",  # Everlong – Foo Fighters
    "7qEHsqek33rTcFNT9PFqLf",  # Ed Sheeran – Happier (just as another example)
    "5YqFhQ1sZs4ERzqF2QYBNS",  # Weezer – Buddy Holly
]

# Clear the playlist first, then add the test songs
sp.playlist_replace_items(PLAYLIST_ID, track_ids)
print(f"Updated 'My Daily DJ' with {len(track_ids)} track(s).")
