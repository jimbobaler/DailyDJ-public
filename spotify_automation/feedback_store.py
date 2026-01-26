from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable


def append_event(path: Path, event: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def load_state(path: Path, *, artist_like_threshold: int = 5) -> Dict:
    if not path.exists():
        return {
            "artist_last_seen": {},
            "track_last_seen": {},
            "liked_by_uri": set(),
            "liked_by_artist": {},
            "learned_boost_artists": set(),
        }
    artist_last: Dict[str, str] = {}
    track_last: Dict[str, str] = {}
    liked_by_uri = set()
    liked_by_artist: Dict[str, int] = {}
    learned_boost = set()

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = event.get("timestamp")
            if not timestamp:
                continue
            ts = timestamp
            etype = event.get("type", "")
            if etype == "generated":
                for uri in event.get("picks", []):
                    track_id = uri.rsplit(":", 1)[-1].lower()
                    track_last[track_id] = ts
                for track_id in event.get("track_ids", []):
                    track_last[track_id.lower()] = ts
                for artist in event.get("artists", []):
                    artist_last[artist.lower()] = ts
            if etype == "like_track":
                uri = event.get("track_uri")
                artist = event.get("artist", "")
                if uri:
                    liked_by_uri.add(uri.lower())
                if artist:
                    key = artist.lower()
                    liked_by_artist[key] = liked_by_artist.get(key, 0) + 1
            if etype == "boost_artist_auto":
                artist = event.get("artist", "")
                if artist:
                    learned_boost.add(artist.lower())

    for artist, count in liked_by_artist.items():
        if count >= artist_like_threshold:
            learned_boost.add(artist)

    return {
        "artist_last_seen": artist_last,
        "track_last_seen": track_last,
        "liked_by_uri": liked_by_uri,
        "liked_by_artist": liked_by_artist,
        "learned_boost_artists": learned_boost,
    }


def record_generated_event(
    path: Path,
    *,
    picks: Iterable[str],
    energy_tag: str,
    discovery_ratio: float,
    candidate_count: int,
) -> None:
    append_event(
        path,
        {
            "type": "generated",
            "timestamp": datetime.utcnow().isoformat(),
            "energy_tag": energy_tag,
            "discovery_ratio": discovery_ratio,
            "candidate_count": candidate_count,
            "picks": list(picks),
        },
    )


def record_like_event(path: Path, *, track_uri: str, artist: str) -> None:
    append_event(
        path,
        {
            "type": "like_track",
            "timestamp": datetime.utcnow().isoformat(),
            "track_uri": track_uri,
            "artist": artist,
        },
    )


def record_boost_artist_event(path: Path, *, artist: str, count: int) -> None:
    append_event(
        path,
        {
            "type": "boost_artist_auto",
            "timestamp": datetime.utcnow().isoformat(),
            "artist": artist,
            "reason": "like_threshold",
            "count": count,
        },
    )
