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
    listening_history=[TrackCandidate("id1", "Song", "Artist")],
    track_pool=[TrackCandidate("id2", "New Song", "Fresh Artist")],
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

- `settings.json` – playlist id/name, discovery ratio, playlist limits, GPT flags.
- `user_profile.json` – short profile lines passed to GPT.
- `rules.json` – banned / reduced artists plus any future rule lists.

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

## Tests

Unit tests for the GPT helper live under `tests/`. Run them with:

```
python3 -m unittest discover -s tests
```
