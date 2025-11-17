import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPE = "playlist-modify-private playlist-read-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))

USER_ID = sp.current_user()["id"]
PLAYLIST_NAME = "My Daily DJ"

# look for an existing playlist with that name
playlists = sp.current_user_playlists(limit=50)["items"]
pl = next((p for p in playlists if p["name"] == PLAYLIST_NAME), None)

if pl:
    print(f"Playlist already exists: {pl['name']} ({pl['id']})")
else:
    pl = sp.user_playlist_create(
        USER_ID,
        PLAYLIST_NAME,
        public=False,
        description="Auto-generated daily playlist"
    )
    print(f"Created new playlist: {pl['name']} ({pl['id']})")
