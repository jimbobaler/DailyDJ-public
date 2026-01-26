# DailyDJ

## GPT-powered recommendations

The `spotify_automation/gpt_recommender.py` module wires ChatGPT into the
playlist builder.  It provides:

1. `GPTRequestBuilder` - builds a deterministic JSON-only prompt that shares the
   user profile, rules, listening history, and an excerpt of the Spotify track
   pool.
2. `GPTResponseParser` - validates the JSON response and turns it into
   `GPTRecommendation` instances.
3. `merge_gpt_recommendations` - mixes GPT discoveries with the deterministic
   track list while respecting the configured discovery percentage.

Example usage:

```python
from spotify_automation.gpt_recommender import (
    TrackCandidate,
    RecommendationContext,
    GPTRequestBuilder,
    GPTResponseParser,
    OpenAIChatCompletionClient,
    merge_gpt_recommendations,
)

context = RecommendationContext(
    user_profile={"focus": "upbeat coding"},
    rules={"banned_artists": ["the killers"]},
    listening_history=[
        TrackCandidate(track_id="id1", title="Song", artist="Artist")
    ],
    track_pool=[
        TrackCandidate(track_id="id2", title="New Song", artist="Fresh Artist")
    ],
)

builder = GPTRequestBuilder(context, playlist_name="My Daily DJ")
prompt = builder.build(discovery_target=3, total_tracks=30)

client = OpenAIChatCompletionClient()
raw_response = client.complete(prompt)
recommendations = GPTResponseParser().parse(raw_response)

final_tracks, warnings = merge_gpt_recommendations(
    base_tracks=context.track_pool,
    track_pool=context.track_pool,
    gpt_recommendations=recommendations,
    total_limit=30,
    discovery_ratio=0.1,
)
```

## Configuration

The refresh script reads user information from JSON files under
`spotify_automation/config/`:

- `settings.json` – playlist id/name, discovery ratio, playlist limits, GPT flags,
  `target_duration_minutes`, and `no_repeat_days`.
- `user_profile.json` – short profile lines passed to GPT.
- `rules.json` – banned / reduced artists plus any future rule lists.
- `taste_profile.yaml` – hard_bans/avoid/boost/like lists, constraints (per-artist cap, cooldowns,
  optional dedupe), vibe tags, and per-mode overrides (e.g., friday discovery ratio).

Tweak those files before running `python3 spotify_automation/daily_dj_refresh.py`.
If you store secrets such as `OPENAI_API_KEY` in a repo-level `.env`, the script
will load it automatically before contacting the APIs.

## GPT toolkit

- `spotify_automation/run_gpt_recommender.py` lets you run the GPT module without
  touching Spotify: it pulls candidates from `track_history.db`, builds the GPT
  prompt, prints the merged playlist, and logs results under
  `spotify_automation/data/gpt_history.jsonl`.
- `spotify_automation/daily_dj_refresh.py` now records every GPT-assisted run in
  the same JSONL file so you can audit reasons/confidence later on.

### Running inside the virtualenv

Use `./scripts/run_in_venv.sh` to ensure every script uses the repo's virtualenv:

```
./scripts/run_in_venv.sh spotify_automation/bulk_load_tracks.py --dry-run
```

There is also a `Makefile` with shortcuts:

```
make refresh     # runs daily_dj_refresh.py
make bulk-load   # loads curated tracks from data/gpt_bulk_tracks.json
make run-gpt     # manual GPT run without touching Spotify
make tests       # python -m unittest discover -s tests
```

## Bulk loading curated tracks

When you want ChatGPT to add a batch of vetted tracks, place them in
`spotify_automation/data/gpt_bulk_tracks.json` (each entry can be a track ID,
Spotify URL, and optional energy tag). Then run:

```
python3 spotify_automation/bulk_load_tracks.py
```

The loader fetches metadata from Spotify, writes the songs into
`track_history.db`, and supports options like `--dry-run` or `--default-energy-tag`
for quick tagging.

## Taste profile and feedback

- Edit `spotify_automation/config/taste_profile.yaml` to set `hard_bans`, `avoid`, `boost`,
  constraints (`max_tracks_per_artist`, `cooldown_days_same_track`, `cooldown_days_same_artist`,
  optional dedupe), vibe tags, and per-mode overrides like `modes.friday.discovery_ratio`.
- Hard bans are enforced in code; GPT cannot select them. GPT is also forced to pick only from
  the provided Spotify candidate pool and must return strict JSON with track URIs.
- Feedback events are written to `spotify_automation/state/feedback.jsonl` (type `generated`),
  and influence scoring via fatigue on recently seen artists/tracks. Playlist runs are logged in
  `track_history.db` tables `playlist_runs` and `playlist_run_tracks`.
- Optional CLI flags on `run_gpt_recommender.py`: `--taste-profile` and `--feedback-store`
  to point at alternate configs/stores.

## Full system documentation
See `docs/DailyDJ.md` for a complete overview, component map, data layout, flow, usage, and troubleshooting.

## Runtime home
- Set `DAILYDJ_HOME` to choose where runtime state lives (default: `~/.dailydj`).
- Stored there: `track_history.db`, `config/`, `data/gpt_history.jsonl`, `state/feedback.jsonl`, and Spotify token cache. If `DAILYDJ_HOME` is unset and the home does not exist, legacy repo-relative paths are used.
- To migrate manually: create the home directory, move your DB/config/data/state files (and `.cache` token if desired) into it, then set `DAILYDJ_HOME`.

## Tests

Unit tests for the GPT helper live under `tests/`. Run them with:

```
python3 -m unittest discover -s tests
```
