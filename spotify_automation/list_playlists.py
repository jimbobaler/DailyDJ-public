import spotipy
from spotipy.oauth2 import SpotifyOAuth

# define the permissions we need
scope = "playlist-read-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))

# get all your playlists
playlists = sp.current_user_playlists(limit=50)

print("\n=== Your Playlists ===")
for pl in playlists["items"]:
    public = "public" if pl["public"] else "private"
    print(f"{pl['name']}  |  {public}  |  {pl['id']}")
print("======================\n")
