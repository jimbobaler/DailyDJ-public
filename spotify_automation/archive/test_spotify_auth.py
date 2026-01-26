import spotipy
from spotipy.oauth2 import SpotifyOAuth

scope = "playlist-read-private playlist-modify-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))

user = sp.current_user()
print(f"Logged in as: {user['display_name']} ({user['id']})")

