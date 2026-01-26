"""
Bulk loader that adds curated Spotify tracks to track_history.db.

Usage:
    python3 spotify_automation/bulk_load_tracks.py \
        --input spotify_automation/data/gpt_bulk_tracks.json

Each JSON entry can be either:
    - a string Spotify track ID or URL
    - an object with keys:
        {
            "track_id": "...",        # or "spotify_url"
            "energy_tag": "monday",   # optional
            "source": "gpt",          # optional
            "note": "optional note"
        }

This script fetches metadata from Spotify to ensure artist/title are correct,
then stores them in the SQLite history so they can be used during refreshes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from spotify_automation import paths

DB_PATH = paths.db_path()
DEFAULT_DATA = paths.data_dir() / "gpt_bulk_tracks.json"
SCOPE = "playlist-modify-private playlist-read-private"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk-load curated tracks.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DATA,
        help="Path to JSON file containing curated tracks.",
    )
    parser.add_argument(
        "--source",
        default="gpt_bulk",
        help="Value for the 'source' column when not provided per entry.",
    )
    parser.add_argument(
        "--default-energy-tag",
        dest="default_energy_tag",
        default=None,
        help="Fallback energy tag applied if entry does not specify one.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch metadata but skip database writes.",
    )
    return parser.parse_args()


def read_entries(path: Path) -> List[Dict[str, Optional[str]]]:
    if not path.exists():
        legacy = Path(__file__).resolve().parent / "data" / "gpt_bulk_tracks.json"
        if legacy.exists():
            path = legacy
        else:
            raise FileNotFoundError(f"Input file not found: {path}")
    data = json.loads(path.read_text())
    entries: List[Dict[str, Optional[str]]] = []
    for entry in data:
        if isinstance(entry, str):
            entries.append({"track_id": entry})
        elif isinstance(entry, dict):
            entries.append(entry)
        else:
            raise ValueError(f"Unsupported entry type: {entry}")
    return entries


def extract_track_id(value: str) -> str:
    value = value.strip()
    if value.startswith("http"):
        value = value.split("?")[0]
        if "/track/" in value:
            return value.rsplit("/track/", 1)[-1]
    return value


def fetch_metadata(sp: spotipy.Spotify, track_ids: Iterable[str]) -> Dict[str, Dict]:
    metadata: Dict[str, Dict] = {}
    ids = list(dict.fromkeys(track_ids))
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        results = sp.tracks(chunk)
        for track in results["tracks"]:
            if track is None:
                continue
            artists = ", ".join(artist["name"] for artist in track["artists"])
            metadata[track["id"]] = {
                "artist": artists,
                "title": track["name"],
                "duration_ms": track.get("duration_ms"),
            }
    return metadata


def insert_tracks(
    rows: List[Dict[str, Optional[str]]],
    *,
    default_source: str,
    default_energy_tag: Optional[str],
    dry_run: bool,
    ) -> None:
    if dry_run:
        print("Dry run: skipping database insert.")
        for row in rows:
            duration = row.get("duration_ms") or 0
            minutes = duration / 60000 if duration else 0
            print(
                f"Would insert {row['artist']} – {row['title']} ({row['track_id']}) "
                f"[{minutes:.1f} min]"
            )
        return

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for row in rows:
            energy = row.get("energy_tag") or default_energy_tag
            cursor.execute(
                """
                INSERT OR REPLACE INTO tracks
                (track_id, artist, title, last_played, source, energy_tag, duration_ms)
                VALUES (?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    row["track_id"],
                    row["artist"],
                    row["title"],
                    row.get("source") or default_source,
                    energy,
                    row.get("duration_ms"),
                ),
            )
        conn.commit()
    print(f"Inserted {len(rows)} tracks into {DB_PATH}.")


def main() -> None:
    args = parse_args()
    _load_env_file(Path(__file__).resolve().parent.parent / ".env")
    paths.cache_dir().mkdir(parents=True, exist_ok=True)
    sp = spotipy.Spotify(
        auth_manager=SpotifyOAuth(scope=SCOPE, cache_path=str(paths.cache_dir() / ".cache"))
    )

    entries = read_entries(args.input)
    track_ids = []
    per_entry: List[Dict[str, Optional[str]]] = []
    for entry in entries:
        value = entry.get("track_id") or entry.get("spotify_url")
        if not value:
            raise ValueError(f"Entry missing track identifier: {entry}")
        track_id = extract_track_id(value)
        per_entry.append(
            {
                "track_id": track_id,
                "energy_tag": entry.get("energy_tag"),
                "source": entry.get("source"),
                "note": entry.get("note"),
            }
        )
        track_ids.append(track_id)

    metadata = fetch_metadata(sp, track_ids)
    missing = [tid for tid in track_ids if tid not in metadata]
    if missing:
        raise ValueError(f"Could not fetch metadata for: {', '.join(missing)}")

    load_rows: List[Dict[str, Optional[str]]] = []
    for entry in per_entry:
        info = metadata[entry["track_id"]]
        load_rows.append(
            {
                "track_id": entry["track_id"],
                "artist": info["artist"],
                "title": info["title"],
                "energy_tag": entry.get("energy_tag"),
                "source": entry.get("source"),
                "duration_ms": info.get("duration_ms"),
            }
        )

    insert_tracks(
        load_rows,
        default_source=args.source,
        default_energy_tag=args.default_energy_tag,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
