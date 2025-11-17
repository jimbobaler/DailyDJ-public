from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
from datetime import date
import subprocess
import json

DB_PATH = "track_history.db"
PLAYLIST_ID = "1rDydhUJnGuHZ2x472nQuW"

app = FastAPI(title="Local Spotify Automation API")

class Track(BaseModel):
    artist: str
    title: str
    track_id: str
    source: str = ""
    energy_tag: str = ""

@app.get("/tracks/recent/{days}")
def recent_tracks(days: int = 30):
    cutoff = str(date.today().fromordinal(date.today().toordinal() - days))
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT artist,title,last_played FROM tracks WHERE last_played>=? ORDER BY last_played DESC",
            (cutoff,),
        ).fetchall()
    return [{"artist": r[0], "title": r[1], "last_played": r[2]} for r in rows]

@app.post("/tracks/add")
def add_track(t: Track):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tracks (track_id,artist,title,last_played,source,energy_tag) VALUES (?,?,?,?,?,?)",
            (t.track_id, t.artist, t.title, str(date.today()), t.source, t.energy_tag),
        )
        conn.commit()
    return {"status": "added", "track": t.dict()}

@app.post("/playlist/daily_refresh")
def daily_refresh():
    # This simply calls your existing refresh script
    result = subprocess.run(
        ["python3", "daily_dj_refresh.py"], capture_output=True, text=True
    )
    return {"stdout": result.stdout, "stderr": result.stderr}
