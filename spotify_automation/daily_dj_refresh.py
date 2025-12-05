# daily_dj_refresh.py
import json
import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from gpt_recommender import (
    RecommendationContext,
    RulePreferences,
    TrackCandidate,
    log_recommendations,
    run_gpt_recommender,
)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
DB_PATH = "track_history.db"
GPT_HISTORY_PATH = DATA_DIR / "gpt_history.jsonl"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)

def _load_json(path: Path, fallback: Dict) -> Dict:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"⚠️  Could not parse {path.name}: {exc}")
        return fallback


DEFAULT_SETTINGS: Dict[str, object] = {
    "playlist_id": "1rDydhUJnGuHZ2x472nQuW",
    "playlist_name": "My Daily DJ",
    "timezone_hint": "local time",
    "tracks_per_day": 30,
    "recent_days": 30,
    "discovery_ratio": 0.0,
    "enable_gpt": False,
    "max_history_items": 10,
    "max_pool_snapshot": 12,
}

DEFAULT_BANNED = [
    "the killers",
    "florence and the machine",
    "the 1975",
    "bloc party",
    "twenty one pilots",
]

DEFAULT_REDUCED = [
    "arctic monkeys",
    "the fratellis",
]

_load_env_file(BASE_DIR.parent / ".env")

SCOPE = "playlist-modify-private playlist-read-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))

settings = DEFAULT_SETTINGS | _load_json(CONFIG_DIR / "settings.json", {})
user_profile = _load_json(CONFIG_DIR / "user_profile.json", {})
rules_config = _load_json(CONFIG_DIR / "rules.json", {})

PLAYLIST_ID = settings["playlist_id"]
PLAYLIST_NAME = settings["playlist_name"]
RECENT_DAYS = int(settings["recent_days"])
TRACKS_PER_DAY = int(settings["tracks_per_day"])
DISCOVERY_RATIO = float(settings.get("discovery_ratio", 0.0))
ENABLE_GPT = bool(settings.get("enable_gpt", False))
MAX_HISTORY_ITEMS = int(settings.get("max_history_items", 10))
MAX_POOL_SNAPSHOT = int(settings.get("max_pool_snapshot", 12))
TIMEZONE_HINT = settings.get("timezone_hint", "local time")


def _load_rule_set(key: str, defaults: Iterable[str]) -> List[str]:
    values = [v.lower() for v in rules_config.get(key, [])]
    combined = {*(v.lower() for v in defaults), *values}
    return sorted(combined)


BANNED_ARTISTS = set(_load_rule_set("banned_artists", DEFAULT_BANNED))
REDUCE_FREQUENCY = set(_load_rule_set("reduce_frequency_artists", DEFAULT_REDUCED))
INCREASE_WEIGHT = set(_load_rule_set("increase_weight_artists", []))

RULE_PREFERENCES = RulePreferences(
    banned_artists=sorted(BANNED_ARTISTS),
    reduce_frequency_artists=sorted(REDUCE_FREQUENCY),
    increase_weight_artists=sorted(INCREASE_WEIGHT),
)

ENERGY_LABELS = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


# --- Helpers ---------------------------------------------------------------
def get_recent_track_ids(days: int) -> set[str]:
    cutoff = date.today() - timedelta(days=days)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT track_id FROM tracks WHERE last_played >= ?", (str(cutoff),)
        ).fetchall()
    return {r[0] for r in rows}


def _row_to_candidate(row: Tuple[str, str, str, str, str]) -> TrackCandidate:
    track_id, artist, title, energy_tag, last_played = row
    return TrackCandidate(
        track_id=track_id,
        artist=artist,
        title=title,
        energy_tag=(energy_tag.lower() if energy_tag else None),
        metadata={"last_played": last_played or ""},
    )


def get_candidate_tracks(tag: str) -> List[TrackCandidate]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT track_id, artist, title, energy_tag, last_played
            FROM tracks
            WHERE energy_tag=? OR energy_tag IS NULL
            """,
            (tag,),
        ).fetchall()
    return [_row_to_candidate(row) for row in rows]


def get_recent_history(limit: int) -> List[TrackCandidate]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT track_id, artist, title, energy_tag, last_played
            FROM tracks
            WHERE last_played IS NOT NULL
            ORDER BY last_played DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_candidate(row) for row in rows]


def mark_tracks_played(track_ids: Iterable[str]) -> None:
    today = str(date.today())
    with sqlite3.connect(DB_PATH) as conn:
        for tid in track_ids:
            conn.execute("UPDATE tracks SET last_played=? WHERE track_id=?", (today, tid))
        conn.commit()


def _apply_artist_rules(track: TrackCandidate, recent_ids: set[str]) -> bool:
    if not track.track_id or track.track_id in recent_ids:
        return False
    artist_low = track.artist.lower()
    if any(b in artist_low for b in BANNED_ARTISTS):
        return False
    if any(r in artist_low for r in REDUCE_FREQUENCY) and random.random() < 0.66:
        return False
    return True


def _maybe_run_gpt(
    base_tracks: Sequence[TrackCandidate],
    pool: Sequence[TrackCandidate],
    *,
    run_label: str,
):
    if not ENABLE_GPT or DISCOVERY_RATIO <= 0:
        return list(base_tracks), []

    base_rules = {
        "banned_artists": sorted(BANNED_ARTISTS),
        "reduce_frequency_artists": sorted(REDUCE_FREQUENCY),
        "increase_weight_artists": sorted(INCREASE_WEIGHT),
    }
    for key, value in rules_config.items():
        if key not in base_rules and isinstance(value, list):
            base_rules[key] = value

    context = RecommendationContext(
        user_profile=user_profile,
        rules=base_rules,
        listening_history=get_recent_history(MAX_HISTORY_ITEMS),
        track_pool=list(pool),
        rule_preferences=RULE_PREFERENCES,
    )

    try:
        result = run_gpt_recommender(
            context=context,
            base_tracks=base_tracks,
            playlist_name=PLAYLIST_NAME,
            timezone_hint=TIMEZONE_HINT,
            total_limit=TRACKS_PER_DAY,
            discovery_ratio=DISCOVERY_RATIO,
            max_history_items=MAX_HISTORY_ITEMS,
            max_pool_snapshot=MAX_POOL_SNAPSHOT,
        )
        if result.gpt_recommendations:
            log_recommendations(result.tracks, GPT_HISTORY_PATH, run_label=run_label)
        return result.tracks, result.warnings
    except Exception as exc:  # pragma: no cover - network/SDK errors
        warning = f"GPT recommender skipped: {exc}"
        return list(base_tracks), [warning]


def _summarize_tracks(tracks: Sequence[TrackCandidate]) -> None:
    print(f"Added {len(tracks)} new tracks:\n")
    for track in tracks[:10]:
        reason = track.metadata.get("gpt_reason")
        if reason:
            print(f" • {track.artist} – {track.title}  (GPT: {reason})")
        else:
            print(f" • {track.artist} – {track.title}")


def main() -> None:
    today_index = date.today().weekday()
    energy_tag = ENERGY_LABELS[today_index]
    print(f"\n🎧 Building playlist for {energy_tag.capitalize()}...")

    recent = get_recent_track_ids(RECENT_DAYS)
    candidates = get_candidate_tracks(energy_tag)

    eligible = [t for t in candidates if _apply_artist_rules(t, recent)]

    if not eligible:
        raise RuntimeError("No eligible tracks found — check DB or filters.")

    random.shuffle(eligible)
    base_selection = eligible[:TRACKS_PER_DAY]

    final_tracks, gpt_warnings = _maybe_run_gpt(
        base_selection,
        eligible,
        run_label=f"{date.today().isoformat()}-{energy_tag}",
    )
    track_ids = [t.track_id for t in final_tracks if t.track_id]

    if not track_ids:
        raise RuntimeError("No track IDs available to update the playlist.")

    sp.playlist_replace_items(PLAYLIST_ID, track_ids)
    mark_tracks_played(track_ids)

    print(f"✅ {PLAYLIST_NAME} refreshed for {energy_tag.capitalize()}")
    _summarize_tracks(final_tracks)
    if gpt_warnings:
        print("\nGPT notices:")
        for w in gpt_warnings:
            print(f" - {w}")


if __name__ == "__main__":
    main()
