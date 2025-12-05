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
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List

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
DB_PATH = BASE_DIR / "track_history.db"
DEFAULT_LOG = DATA_DIR / "gpt_history.jsonl"


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
    return parser.parse_args()


def _load_json(path: Path, fallback: Dict) -> Dict:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return fallback


def _fetch_tracks(tag: str | None, limit: int) -> List[TrackCandidate]:
    clause = ""
    params: List[str] = []
    if tag:
        clause = "WHERE energy_tag=? OR energy_tag IS NULL"
        params.append(tag)

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT track_id, artist, title, energy_tag, last_played
            FROM tracks
            {clause}
            ORDER BY last_played IS NULL, last_played DESC
            LIMIT ?
            """,
            (*params, limit * 3),
        ).fetchall()

    return [
        TrackCandidate(
            track_id=row[0],
            artist=row[1],
            title=row[2],
            energy_tag=(row[3].lower() if row[3] else None),
            metadata={"last_played": row[4] or ""},
        )
        for row in rows
    ]


def _fetch_history(limit: int) -> List[TrackCandidate]:
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
    return [
        TrackCandidate(
            track_id=row[0],
            artist=row[1],
            title=row[2],
            energy_tag=(row[3].lower() if row[3] else None),
            metadata={"last_played": row[4] or ""},
        )
        for row in rows
    ]


def _build_rule_preferences(rules: Dict[str, Iterable[str]]) -> RulePreferences:
    return RulePreferences(
        banned_artists=sorted(rules.get("banned_artists", [])),
        reduce_frequency_artists=sorted(rules.get("reduce_frequency_artists", [])),
        increase_weight_artists=sorted(rules.get("increase_weight_artists", [])),
    )


def main() -> None:
    _load_env_file(BASE_DIR.parent / ".env")
    args = parse_args()
    settings = _load_json(
        CONFIG_DIR / "settings.json",
        {"playlist_name": "My Daily DJ", "timezone_hint": "local time"},
    )
    user_profile = _load_json(CONFIG_DIR / "user_profile.json", {})
    rules = _load_json(CONFIG_DIR / "rules.json", {})
    track_pool = _fetch_tracks(args.energy_tag, args.limit)
    base_selection = track_pool[: args.limit]

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
    )

    if result.gpt_recommendations:
        log_recommendations(
            result.tracks,
            args.log_path,
            run_label=f"manual-{date.today().isoformat()}",
        )

    print(f"Generated {len(result.tracks)} tracks (GPT picks: {len(result.gpt_recommendations)})")
    for track in result.tracks:
        reason = track.metadata.get("gpt_reason")
        extra = f" — GPT: {reason}" if reason else ""
        print(f"- {track.artist} – {track.title}{extra}")
    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"* {warning}")


if __name__ == "__main__":
    main()
