"""
GPT-powered recommendation helpers for Spotify DJ.

This module keeps the GPT integration isolated so the rest of the playlist
pipeline can stay deterministic and easy to test.  The main pieces are:

- ``GPTRequestBuilder``: Builds a structured prompt based on the user's rules,
  history, and Spotify track pool.
- ``GPTResponseParser``: Validates that GPT responded with the agreed JSON
  schema and converts it to ``GPTRecommendation`` objects.
- ``merge_gpt_recommendations``: Merges GPT discoveries into the deterministic
  Spotify track list while respecting the configured discovery percentage.

Nothing in here talks directly to Spotipy; callers only need to provide simple
``TrackCandidate`` objects, so the module can be unit tested without hitting
any external API.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

try:
    # ``openai`` is optional so the module can still be imported for testing.
    from openai import OpenAI
except ImportError:  # pragma: no cover - the project may not have openai yet
    OpenAI = None

logger = logging.getLogger(__name__)


# --- Domain objects --------------------------------------------------------
@dataclass(frozen=True)
class TrackCandidate:
    """Simplified representation of a Spotify track we can reason about."""

    track_id: str
    title: str
    artist: str
    album: Optional[str] = None
    energy_tag: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RulePreferences:
    """Structured rules for GPT prompts and weighting logic."""

    banned_artists: Sequence[str] = ()
    reduce_frequency_artists: Sequence[str] = ()
    increase_weight_artists: Sequence[str] = ()

    def to_prompt_lines(self) -> List[str]:
        def fmt(name: str, items: Sequence[str]) -> str:
            payload = ", ".join(items) if items else "none"
            return f"- {name}: {payload}"

        return [
            fmt("banned_artists", self.banned_artists),
            fmt("reduce_frequency_artists", self.reduce_frequency_artists),
            fmt("increase_weight_artists", self.increase_weight_artists),
        ]


@dataclass(frozen=True)
class GPTRecommendation:
    """Normalized recommendation coming back from GPT."""

    title: str
    artist: str
    reason: str
    energy_tag: Optional[str] = None
    spotify_track_id: Optional[str] = None
    confidence: float = 0.5


@dataclass(frozen=True)
class RecommendationContext:
    """
    Snapshot of data describing the user and their current playlist needs.
    """

    user_profile: Dict[str, str]
    rules: Dict[str, Sequence[str]]
    listening_history: Sequence[TrackCandidate]
    track_pool: Sequence[TrackCandidate]
    rule_preferences: Optional[RulePreferences] = None


@dataclass(frozen=True)
class RecommendationRunResult:
    """Bundle returned by run_gpt_recommender."""

    tracks: List[TrackCandidate]
    warnings: List[str]
    gpt_recommendations: List[GPTRecommendation]


# --- GPT wiring ------------------------------------------------------------
class CompletionClient(Protocol):
    """Tiny protocol so we can swap out the actual GPT client in tests."""

    def complete(self, prompt: str) -> str:  # pragma: no cover - interface only
        ...


class OpenAIChatCompletionClient:
    """
    Small adapter around the OpenAI SDK so the recommender can stay decoupled.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        system_prompt: str = "You are a meticulous musicologist.",
    ):
        if OpenAI is None:  # pragma: no cover - depends on optional dependency
            raise ImportError(
                "openai package is required for OpenAIChatCompletionClient"
            )
        self._client = OpenAI()
        self._model = model
        self._temperature = temperature
        self._system_prompt = system_prompt

    def complete(self, prompt: str) -> str:
        """
        Issues a chat completion and returns the assistant message text.
        """
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""


# --- Prompt assembly -------------------------------------------------------
class GPTRequestBuilder:
    """
    Builds a deterministic, well-structured prompt for GPT.
    """

    def __init__(
        self,
        context: RecommendationContext,
        playlist_name: str,
        timezone_hint: str = "local time",
        max_history_items: int = 10,
        max_pool_snapshot: int = 12,
    ):
        self.context = context
        self.playlist_name = playlist_name
        self.timezone_hint = timezone_hint
        self.max_history_items = max_history_items
        self.max_pool_snapshot = max_pool_snapshot

    def build(self, discovery_target: int, total_tracks: int) -> str:
        """
        Returns the full user prompt sent to GPT.
        """
        profile_lines = self._format_profile()
        rules_lines = self._format_rules()
        history_lines = self._format_tracks(
            self.context.listening_history[: self.max_history_items]
        )
        pool_lines = self._format_tracks(
            self.context.track_pool[: self.max_pool_snapshot]
        )

        instructions = (
            "You must recommend songs that feel like a continuation of the "
            f"user's taste. Select exactly {discovery_target} new discovery "
            "tracks that are not already in the user's history."
        )
        schema = json.dumps(
            {
                "recommendations": [
                    {
                        "title": "Song title",
                        "artist": "Artist name",
                        "energy_tag": "monday / tuesday / ... or null",
                        "spotify_track_id": "optional Spotify track id string",
                        "reason": "1 short sentence",
                        "confidence": 0.0,
                    }
                ]
            },
            indent=2,
        )

        prompt = f"""
I need help programming a playlist called "{self.playlist_name}". Timezone: {self.timezone_hint}.

Profile:
{profile_lines}

Rules:
{rules_lines}

Recently loved tracks:
{history_lines}

Current Spotify pool snapshot:
{pool_lines}

{instructions}

Return ONLY valid JSON that matches this schema:
{schema}
"""
        return "\n".join(line.rstrip() for line in prompt.strip().splitlines())

    def _format_profile(self) -> str:
        if not self.context.user_profile:
            return "- (no profile provided)"
        return "\n".join(f"- {k}: {v}" for k, v in self.context.user_profile.items())

    def _format_rules(self) -> str:
        if not self.context.rules:
            lines = ["- (no rules provided)"]
        else:
            lines = []
            for rule, values in self.context.rules.items():
                payload = ", ".join(values) if values else "none"
                lines.append(f"- {rule}: {payload}")
        if self.context.rule_preferences:
            lines.append("")
            lines.append("Preference summary:")
            lines.extend(self.context.rule_preferences.to_prompt_lines())
        return "\n".join(lines)

    def _format_tracks(self, tracks: Sequence[TrackCandidate]) -> str:
        if not tracks:
            return "- none"
        return "\n".join(
            f"- {t.artist} – {t.title}"
            + (f" [{t.energy_tag}]" if t.energy_tag else "")
            for t in tracks
        )


# --- Response parsing ------------------------------------------------------
class GPTResponseParser:
    """
    Ensures GPT output matches the expected schema.
    """

    def parse(self, response_text: str) -> List[GPTRecommendation]:
        """
        Parse the raw assistant response and return normalized recommendations.
        """
        json_text = self._extract_json(response_text)
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ValueError("GPT response was not valid JSON") from exc

        recs = payload.get("recommendations")
        if not isinstance(recs, list):
            raise ValueError("GPT response missing 'recommendations' list")

        recommendations: List[GPTRecommendation] = []
        for rec in recs:
            recommendations.append(self._parse_rec(rec))
        return recommendations

    def _parse_rec(self, data: Dict[str, object]) -> GPTRecommendation:
        required_fields = ("title", "artist", "reason")
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValueError(f"GPT response missing '{field}' in entry")

        conf = float(data.get("confidence", 0.5))
        conf = max(0.0, min(1.0, conf))

        energy_tag = data.get("energy_tag")
        if energy_tag is not None:
            energy_tag = str(energy_tag).lower()

        track_id = data.get("spotify_track_id")
        if track_id is not None:
            track_id = str(track_id)

        return GPTRecommendation(
            title=str(data["title"]),
            artist=str(data["artist"]),
            reason=str(data["reason"]),
            energy_tag=energy_tag or None,
            spotify_track_id=track_id or None,
            confidence=conf,
        )

    def _extract_json(self, text: str) -> str:
        """
        GPT sometimes wraps JSON in ```json fences. Strip those first.
        """
        if "```" not in text:
            return text.strip()
        match = re.search(r"```(?:json)?\s*(.*)```", text, re.DOTALL)
        if not match:
            return text.strip()
        return match.group(1).strip()


# --- Merging logic ---------------------------------------------------------
def merge_gpt_recommendations(
    *,
    base_tracks: Sequence[TrackCandidate],
    track_pool: Sequence[TrackCandidate],
    gpt_recommendations: Sequence[GPTRecommendation],
    total_limit: int,
    discovery_ratio: float,
    rule_preferences: Optional[RulePreferences] = None,
) -> Tuple[List[TrackCandidate], List[str]]:
    """
    Merge GPT discoveries into the base track list while keeping ratios sane.

    Returns a tuple of (final_tracks, warnings).
    """
    if total_limit <= 0:
        return [], ["total_limit must be positive"]

    discovery_target = max(0, min(total_limit, round(total_limit * discovery_ratio)))
    pool_index = _build_track_index(track_pool)

    matched_discoveries, warnings = _match_recommendations(
        gpt_recommendations, pool_index
    )
    matched_discoveries = matched_discoveries[:discovery_target]

    final_tracks: List[TrackCandidate] = []
    seen_ids = set()

    def add_track(track: TrackCandidate):
        if track.track_id in seen_ids:
            return
        final_tracks.append(track)
        seen_ids.add(track.track_id)

    for track in matched_discoveries:
        add_track(track)

    for track in base_tracks:
        if len(final_tracks) >= total_limit:
            break
        add_track(track)

    if len(final_tracks) < total_limit:
        remaining_pool = [
            t
            for t in track_pool
            if t.track_id not in seen_ids
        ]
        for track in remaining_pool:
            if len(final_tracks) >= total_limit:
                break
            add_track(track)

    final_tracks = final_tracks[:total_limit]
    if rule_preferences:
        final_tracks.sort(
            key=lambda track: _preference_weight(track, rule_preferences), reverse=True
        )

    return final_tracks, warnings


def _build_track_index(
    pool: Sequence[TrackCandidate],
) -> Dict[str, TrackCandidate]:
    index: Dict[str, TrackCandidate] = {}
    for track in pool:
        if track.track_id:
            index[track.track_id.lower()] = track
        key = _normalize_key(track.artist, track.title)
        index[key] = track
    return index


def _match_recommendations(
    recommendations: Sequence[GPTRecommendation],
    index: Dict[str, TrackCandidate],
) -> Tuple[List[TrackCandidate], List[str]]:
    matched: List[TrackCandidate] = []
    warnings: List[str] = []
    for rec in recommendations:
        track = None
        if rec.spotify_track_id:
            track = index.get(rec.spotify_track_id.lower())
        if track is None:
            track = index.get(_normalize_key(rec.artist, rec.title))
        if track is None:
            warnings.append(
                f"GPT recommended '{rec.artist} – {rec.title}', but it was not in the Spotify pool."
            )
            continue
        enriched = replace(
            track,
            metadata={
                **track.metadata,
                "gpt_reason": rec.reason,
                "gpt_confidence": f"{rec.confidence:.2f}",
            },
        )
        matched.append(enriched)
    return matched, warnings


def _preference_weight(track: TrackCandidate, prefs: RulePreferences) -> float:
    artist = track.artist.lower()
    weight = 1.0
    if any(artist == item.lower() for item in prefs.increase_weight_artists):
        weight *= 1.3
    if any(artist == item.lower() for item in prefs.reduce_frequency_artists):
        weight *= 0.7
    if any(artist == item.lower() for item in prefs.banned_artists):
        weight *= 0.1
    return weight


def _normalize_key(artist: str, title: str) -> str:
    normalize = lambda value: re.sub(r"\s+", " ", value).strip().lower()
    return f"{normalize(artist)}::{normalize(title)}"


def log_recommendations(
    tracks: Sequence[TrackCandidate],
    destination: Path,
    *,
    run_label: str,
) -> None:
    """
    Append GPT decisions to a JSONL file so we keep provenance.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with destination.open("a", encoding="utf-8") as handle:
        for track in tracks:
            payload = {
                "run_label": run_label,
                "timestamp": timestamp,
                "track_id": track.track_id,
                "artist": track.artist,
                "title": track.title,
                "energy_tag": track.energy_tag,
                "metadata": track.metadata,
            }
            handle.write(json.dumps(payload) + "\n")


def run_gpt_recommender(
    *,
    context: RecommendationContext,
    base_tracks: Sequence[TrackCandidate],
    playlist_name: str,
    timezone_hint: str,
    total_limit: int,
    discovery_ratio: float,
    completion_client: Optional[CompletionClient] = None,
    max_history_items: int = 10,
    max_pool_snapshot: int = 12,
) -> RecommendationRunResult:
    """
    High-level helper that handles prompt/response/merge flow.
    """
    if discovery_ratio <= 0:
        return RecommendationRunResult(list(base_tracks), [], [])

    builder = GPTRequestBuilder(
        context,
        playlist_name=playlist_name,
        timezone_hint=timezone_hint,
        max_history_items=max_history_items,
        max_pool_snapshot=max_pool_snapshot,
    )
    parser = GPTResponseParser()
    client = completion_client or OpenAIChatCompletionClient()

    prompt = builder.build(
        discovery_target=max(1, round(total_limit * discovery_ratio)),
        total_tracks=total_limit,
    )
    raw_response = client.complete(prompt)
    recommendations = parser.parse(raw_response)
    final_tracks, warnings = merge_gpt_recommendations(
        base_tracks=base_tracks,
        track_pool=context.track_pool,
        gpt_recommendations=recommendations,
        total_limit=total_limit,
        discovery_ratio=discovery_ratio,
        rule_preferences=context.rule_preferences,
    )
    return RecommendationRunResult(final_tracks, warnings, recommendations)


__all__ = [
    "TrackCandidate",
    "GPTRecommendation",
    "RecommendationContext",
    "RecommendationRunResult",
    "RulePreferences",
    "CompletionClient",
    "OpenAIChatCompletionClient",
    "GPTRequestBuilder",
    "GPTResponseParser",
    "merge_gpt_recommendations",
    "log_recommendations",
    "run_gpt_recommender",
]
