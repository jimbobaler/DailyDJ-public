"""
CLI helper to run the GPT recommender outside of the daily refresh.

Example:
    python3 spotify_automation/run_gpt_recommender.py --energy-tag friday
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpt_recommender import (
    GPTRecommendation,
    RecommendationContext,
    RulePreferences,
    TrackCandidate,
    log_recommendations,
    run_gpt_recommender,
)
from spotify_automation.feedback_store import load_state
from spotify_automation.taste_profile import load_taste_profile

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR.parent / "track_history.db"
DEFAULT_LOG = DATA_DIR / "gpt_history.jsonl"
SCOPE = "playlist-read-private"
DEFAULT_BANNED = {
    "the killers",
    "florence and the machine",
    "the 1975",
    "bloc party",
    "twenty one pilots",
}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run GPT recommender standalone.")
    parser.add_argument("--energy-tag", default=None, help="Filter track pool by tag.")
    parser.add_argument(
        "--limit", type=int, default=30, help="Total playlist target size."
    )
    parser.add_argument(
        "--discovery-ratio",
        type=float,
        default=0.2,
        help="Discovery ratio to blend GPT picks.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=10,
        help="How many history tracks to include in the prompt.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG,
        help="Where to append GPT history (JSONL).",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist resolved tracks into the database for future runs.",
    )
    parser.add_argument(
        "--taste-profile",
        type=Path,
        default=BASE_DIR / "config" / "taste_profile.yaml",
        help="Path to taste profile configuration.",
    )
    parser.add_argument(
        "--feedback-store",
        type=Path,
        default=BASE_DIR / "state" / "feedback.jsonl",
        help="Where to store feedback events (JSONL).",
    )
    return parser.parse_args()


def _load_json(path: Path, fallback: Dict) -> Dict:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return fallback


def _fetch_tracks(tag: str | None, limit: int, banned_ids: set[str]) -> List[TrackCandidate]:
    clause = ""
    params: List[str] = []
    if tag:
        clause = "WHERE energy_tag=? OR energy_tag IS NULL"
        params.append(tag)

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT track_id, artist, title, energy_tag, last_played, duration_ms
            FROM tracks
            {clause}
            ORDER BY last_played IS NULL, last_played DESC
            LIMIT ?
            """,
            (*params, limit * 3),
        ).fetchall()

    results = []
    for row in rows:
        if row[0] in banned_ids:
            continue
        results.append(
            TrackCandidate(
                track_id=row[0],
                artist=row[1],
                title=row[2],
                duration_ms=row[5],
                energy_tag=(row[3].lower() if row[3] else None),
                metadata={"last_played": row[4] or "", "source": "seed"},
            )
        )
    return results


def _fetch_history(limit: int) -> List[TrackCandidate]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT track_id, artist, title, energy_tag, last_played, duration_ms
            FROM tracks
            WHERE last_played IS NOT NULL
            ORDER BY last_played DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        TrackCandidate(
            track_id=row[0],
            artist=row[1],
            title=row[2],
            duration_ms=row[5],
            energy_tag=(row[3].lower() if row[3] else None),
            metadata={"last_played": row[4] or ""},
        )
        for row in rows
    ]


def _get_banned_ids() -> set[str]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT track_id FROM bans").fetchall()
    return {r[0] for r in rows}


def _get_banned_artists() -> set[str]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT artist FROM artist_bans").fetchall()
    return {r[0].lower() for r in rows}


def _build_rule_preferences(rules: Dict[str, Iterable[str]]) -> RulePreferences:
    return RulePreferences(
        banned_artists=sorted(rules.get("banned_artists", [])),
        reduce_frequency_artists=sorted(rules.get("reduce_frequency_artists", [])),
        increase_weight_artists=sorted(rules.get("increase_weight_artists", [])),
    )


def _get_like_threshold(profile: Dict) -> int:
    return int(profile.get("learning", {}).get("artist_like_threshold", 5))


def _search_spotify_for_rec(sp_client: spotipy.Spotify) -> Callable[[GPTRecommendation], Optional[TrackCandidate]]:
    def _inner(rec: GPTRecommendation) -> Optional[TrackCandidate]:
        query = f'track:"{rec.title}" artist:"{rec.artist}"'
        results = sp_client.search(q=query, type="track", limit=3)
        tracks = results.get("tracks", {}).get("items", [])
        if not tracks:
            return None
        match = tracks[0]
        artist_names = ", ".join(a["name"] for a in match.get("artists", []))
        return TrackCandidate(
            track_id=match["id"],
            artist=artist_names,
            title=match.get("name", rec.title),
            duration_ms=match.get("duration_ms"),
            energy_tag=(rec.energy_tag.lower() if rec.energy_tag else None),
            metadata={
                "gpt_reason": rec.reason,
                "gpt_confidence": f"{rec.confidence:.2f}",
                "source": "gpt_discovery",
            },
        )

    return _inner


def _ensure_tracks(tracks: Iterable[TrackCandidate]) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        for track in tracks:
            conn.execute(
                """
                INSERT OR REPLACE INTO tracks
                (track_id, artist, title, last_played, source, energy_tag, duration_ms)
                VALUES (?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    track.track_id,
                    track.artist,
                    track.title,
                    track.metadata.get("source"),
                    track.energy_tag,
                    track.duration_ms,
                ),
            )
        conn.commit()


def _filter_banned(
    tracks: List[TrackCandidate],
    banned_ids: set[str],
    banned_artists: set[str],
) -> List[TrackCandidate]:
    def _norm(name: str) -> str:
        return (
            name.lower()
            .replace("+", " and ")
            .replace("&", " and ")
            .replace("  ", " ")
        )

    banned_normalized = {_norm(b) for b in banned_artists}
    filtered: List[TrackCandidate] = []
    seen = set()
    for track in tracks:
        if not track.track_id or track.track_id in banned_ids:
            continue
        artist_low = _norm(track.artist)
        if any(ban in artist_low for ban in banned_normalized):
            continue
        if track.track_id in seen:
            continue
        seen.add(track.track_id)
        filtered.append(track)
    return filtered


def main() -> None:
    _load_env_file(BASE_DIR.parent / ".env")
    args = parse_args()
    settings = _load_json(
        CONFIG_DIR / "settings.json",
        {"playlist_name": "My Daily DJ", "timezone_hint": "local time"},
    )
    user_profile = _load_json(CONFIG_DIR / "user_profile.json", {})
    rules = _load_json(CONFIG_DIR / "rules.json", {})
    banned_ids = _get_banned_ids()
    banned_artists = (
        {artist.lower() for artist in rules.get("banned_artists", [])}
        | DEFAULT_BANNED
        | _get_banned_artists()
    )
    track_pool = _fetch_tracks(args.energy_tag, args.limit, banned_ids)
    base_selection = track_pool[: args.limit]
    sp_client = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE))
    taste_profile = load_taste_profile(args.taste_profile)
    feedback_state = load_state(
        args.feedback_store, artist_like_threshold=_get_like_threshold(taste_profile)
    )

    context = RecommendationContext(
        user_profile=user_profile,
        rules=rules,
        listening_history=_fetch_history(args.history_limit),
        track_pool=track_pool,
        rule_preferences=_build_rule_preferences(rules),
    )

    result = run_gpt_recommender(
        context=context,
        base_tracks=base_selection,
        playlist_name=settings.get("playlist_name", "My Daily DJ"),
        timezone_hint=settings.get("timezone_hint", "local time"),
        total_limit=args.limit,
        discovery_ratio=args.discovery_ratio,
        max_history_items=args.history_limit,
        max_pool_snapshot=args.limit,
        search_func=_search_spotify_for_rec(sp_client),
        taste_profile=taste_profile,
        feedback_state=feedback_state,
        feedback_path=args.feedback_store,
        energy_tag=args.energy_tag,
    )

    filtered_tracks = _filter_banned(result.tracks, banned_ids, banned_artists)

    if args.save and filtered_tracks:
        _ensure_tracks(filtered_tracks)

    if result.gpt_recommendations:
        log_recommendations(
            filtered_tracks,
            args.log_path,
            run_label=f"manual-{date.today().isoformat()}",
        )

    print(f"Generated {len(filtered_tracks)} tracks (GPT picks: {len(result.gpt_recommendations)})")
    for track in filtered_tracks:
        reason = track.metadata.get("gpt_reason")
        extra = f" — GPT: {reason}" if reason else ""
        print(f"- {track.artist} – {track.title}{extra}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"* {warning}")


if __name__ == "__main__":
    main()
