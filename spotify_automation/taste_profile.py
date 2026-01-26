from __future__ import annotations

import json
import re
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


DEFAULT_PROFILE = {
    "hard_bans": {"artists": [], "tracks": []},
    "avoid": {"artists": [], "tracks": []},
    "boost": {"artists": [], "tracks": []},
    "like": {"artists": [], "tracks": []},
    "track_rules": {"hard_bans": {"tracks": []}, "boost": {"tracks": []}, "avoid": {"tracks": []}},
    "constraints": {
        "max_tracks_per_artist": 2,
        "cooldown_days_same_track": 30,
        "cooldown_days_same_artist": 10,
        "dedupe_title_variants": False,
    },
    "discovery": {
        "ratio_default": 0.0,
        "allowed_similarity": [],
        "discourage_artists": [],
    },
    "scene_anchors": {},
    "scoring": {
        "boost_weight": 1.0,
        "like_weight": 0.5,
        "avoid_weight": -0.5,
        "hard_ban_weight": -9999.0,
        "played_through_bonus": 0.0,
        "skipped_early_penalty": 0.0,
        "recent_play_penalty": {"within_days": 14, "penalty": -1.0},
        "long_time_no_play_bonus": {"after_days": 120, "bonus": 0.0},
    },
    "vibe_tags": [],
    "modes": {},
}


def normalize_text(text: str) -> str:
    lowered = text.lower().replace("&", " and ").replace("+", " and ")
    table = str.maketrans("", "", string.punctuation)
    stripped = lowered.translate(table)
    return re.sub(r"\s+", " ", stripped).strip()


def _load_yaml_like(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None

    content = path.read_text()
    if yaml:
        return yaml.safe_load(content) or {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # fallback: give up and return defaults so callers still have structure
        return {}


def load_taste_profile(path: Path) -> dict:
    if not path.exists():
        return DEFAULT_PROFILE.copy()
    data = _load_yaml_like(path)
    # merge with defaults to ensure keys exist
    profile = json.loads(json.dumps(DEFAULT_PROFILE))
    for key, value in data.items():
        if isinstance(value, dict):
            merged = profile.get(key, {}).copy()
            merged.update(value)
            profile[key] = merged
        else:
            profile[key] = value

    # union track_rules into primary sections
    track_rules = profile.get("track_rules", {})
    hard_tracks = track_rules.get("hard_bans", {}).get("tracks", [])
    if hard_tracks:
        profile["hard_bans"].setdefault("tracks", [])
        profile["hard_bans"]["tracks"] = list({*profile["hard_bans"]["tracks"], *hard_tracks})
    boost_tracks = track_rules.get("boost", {}).get("tracks", [])
    if boost_tracks:
        profile["boost"].setdefault("tracks", [])
        profile["boost"]["tracks"] = list({*profile["boost"]["tracks"], *boost_tracks})
    like_tracks = track_rules.get("like", {}).get("tracks", [])
    if like_tracks:
        profile.setdefault("like", {}).setdefault("tracks", [])
        profile["like"]["tracks"] = list({*profile["like"]["tracks"], *like_tracks})
    avoid_tracks = track_rules.get("avoid", {}).get("tracks", [])
    if avoid_tracks:
        profile["avoid"].setdefault("tracks", [])
        profile["avoid"]["tracks"] = list({*profile["avoid"]["tracks"], *avoid_tracks})

    return profile
    return profile


def is_hard_banned(artist: str, title: str, profile: dict) -> bool:
    norm_artist = normalize_text(artist)
    norm_title = normalize_text(title)
    banned_artists = [normalize_text(a) for a in profile.get("hard_bans", {}).get("artists", [])]
    banned_tracks = [normalize_text(t) for t in profile.get("hard_bans", {}).get("tracks", [])]
    if any(ban in norm_artist for ban in banned_artists):
        return True
    return any(ban in norm_title for ban in banned_tracks)


def _weight(name: str, boosts: Sequence[str], avoids: Sequence[str]) -> float:
    norm = normalize_text(name)
    if any(norm.startswith(normalize_text(item)) or normalize_text(item) in norm for item in boosts):
        return 1.0
    if any(norm.startswith(normalize_text(item)) or normalize_text(item) in norm for item in avoids):
        return -1.0
    return 0.0


def score_track(track, profile: dict, feedback_state: dict, now: datetime) -> float:
    scoring = profile.get("scoring", {})
    boosts = profile.get("boost", {})
    avoids = profile.get("avoid", {})
    likes = profile.get("like", {})
    boost_w = float(scoring.get("boost_weight", 1.0))
    like_w = float(scoring.get("like_weight", 0.5))
    avoid_w = float(scoring.get("avoid_weight", -0.5))
    base = 0.0
    base += boost_w * _weight(track.artist, boosts.get("artists", []), [])
    base += boost_w * _weight(track.title, boosts.get("tracks", []), [])
    base += like_w * _weight(track.artist, likes.get("artists", []), [])
    base += like_w * _weight(track.title, likes.get("tracks", []), [])
    base += avoid_w * abs(_weight(track.artist, [], avoids.get("artists", [])))
    base += avoid_w * abs(_weight(track.title, [], avoids.get("tracks", [])))

    discourage = profile.get("discovery", {}).get("discourage_artists", [])
    if any(normalize_text(item) in normalize_text(track.artist) for item in discourage):
        base += avoid_w

    anchors = profile.get("scene_anchors", {})
    for group in anchors.values():
        if any(normalize_text(item) in normalize_text(track.artist) for item in group):
            base += boost_w * 0.5
            break

    artist_last = feedback_state.get("artist_last_seen", {}).get(track.artist.lower())
    track_last = feedback_state.get("track_last_seen", {}).get(track.track_id.lower())
    recent_cfg = scoring.get("recent_play_penalty", {"within_days": 14, "penalty": -1.0})
    long_cfg = scoring.get("long_time_no_play_bonus", {"after_days": 120, "bonus": 0.0})
    if artist_last:
        delta = now - datetime.fromisoformat(artist_last)
        if delta.days <= recent_cfg.get("within_days", 14):
            base += float(recent_cfg.get("penalty", -1.0))
    if track_last:
        delta = now - datetime.fromisoformat(track_last)
        if delta.days <= recent_cfg.get("within_days", 14):
            base += float(recent_cfg.get("penalty", -1.0))
        if delta.days >= long_cfg.get("after_days", 120):
            base += float(long_cfg.get("bonus", 0.0))

    # learned boosts from feedback (artist-level) and direct liked tracks
    learned_boost_artists = feedback_state.get("learned_boost_artists", set())
    if track.artist.lower() in learned_boost_artists:
        base += 1.5
    liked_by_uri = feedback_state.get("liked_by_uri", set())
    uri = getattr(track, "uri", None)
    if uri and uri.lower() in liked_by_uri:
        base += 3.0
    elif track.track_id and f"spotify:track:{track.track_id}".lower() in liked_by_uri:
        base += 3.0

    return base


def apply_constraints(
    tracks: Iterable,
    profile: dict,
    feedback_state: dict,
    now: datetime,
) -> List:
    constraints = profile.get("constraints", {})
    max_per_artist = int(constraints.get("max_tracks_per_artist", 2))
    cooldown_track = int(constraints.get("cooldown_days_same_track", 30))
    cooldown_artist = int(constraints.get("cooldown_days_same_artist", 10))
    dedupe_titles = bool(constraints.get("dedupe_title_variants", False))

    artist_counts: Dict[str, int] = {}
    seen_titles = set()
    filtered: List = []
    for track in tracks:
        artist_key = track.artist.lower()
        if artist_counts.get(artist_key, 0) >= max_per_artist:
            continue

        last_track_play = feedback_state.get("track_last_seen", {}).get(track.track_id.lower())
        if last_track_play:
            if (now - datetime.fromisoformat(last_track_play)) < timedelta(days=cooldown_track):
                continue

        last_artist_play = feedback_state.get("artist_last_seen", {}).get(artist_key)
        if last_artist_play:
            if (now - datetime.fromisoformat(last_artist_play)) < timedelta(days=cooldown_artist):
                continue

        if dedupe_titles:
            norm_title = normalize_text(track.title)
            if norm_title in seen_titles:
                continue
            seen_titles.add(norm_title)

        artist_counts[artist_key] = artist_counts.get(artist_key, 0) + 1
        filtered.append(track)
    return filtered
