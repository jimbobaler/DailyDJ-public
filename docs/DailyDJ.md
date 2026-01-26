# DailyDJ – System Overview and Usage

## What this system does
- Builds and refreshes a Spotify playlist (My Daily DJ) daily.
- Uses a local SQLite catalog (`track_history.db`) to assemble a candidate pool.
- Applies taste rules (hard bans, avoid/boost/like, cooldowns, per-artist caps, dedupe).
- Can blend GPT picks constrained to the candidate pool (URI-only, strict JSON). Invalid GPT output falls back to deterministic ranking.
- Records runs and feedback to drive fatigue (penalize recent repeats, reward long-gapped plays).

## Components (files)
- `spotify_automation/daily_dj_refresh.py`: Main orchestrator; fetches pool, filters, scores, runs GPT with a URI shortlist, merges/fills, updates Spotify, records run, bans removals.
- `spotify_automation/run_gpt_recommender.py`: Standalone runner for GPT/deterministic selection without touching the playlist; supports `--taste-profile` and `--feedback-store`.
- `spotify_automation/gpt_recommender.py`: Prompt building, URI-only GPT validation, hard-ban checks, scoring, constraints, deterministic fallback.
- `spotify_automation/taste_profile.py`: Loads/normalizes taste profile; scoring (boost/like/avoid), constraints (cooldowns, per-artist cap, dedupe), hard-ban checks.
- `spotify_automation/feedback_store.py`: JSONL feedback store loader/writer (type `generated` events).
- `spotify_automation/migrate_db.py` / `init_db.py`: Create/upgrade SQLite schema (tracks, bans, artist_bans, playlist_runs, playlist_run_tracks).
- `spotify_automation/bulk_load_tracks.py`: Bulk insert curated tracks with metadata.
- Configs: `config/settings.json`, `config/taste_profile.yaml`, `config/user_profile.json`, `config/rules.json`.
- State/logs: `track_history.db` (root), `data/gpt_history.jsonl`, `state/feedback.jsonl`.

## Data and state layout
- **Home directory**: Configurable via `DAILYDJ_HOME` (defaults to `~/.dailydj`). If unset and home does not exist, legacy repo-relative paths under `spotify_automation/` are used.
- **DB (`track_history.db`)**: `tracks` (id, artist, title, energy_tag, duration_ms, last_played, source); `bans` (track-level); `artist_bans`; `playlist_runs` and `playlist_run_tracks` for audit. Stored under home or legacy path.
- **Feedback (fatigue/learning)**: `state/feedback.jsonl` (events: `generated`, `like_track`, `boost_artist_auto`) – used to build last-seen maps, fatigue, and learned boosts. Stored under home/state or legacy.
- **GPT history**: `data/gpt_history.jsonl` (append-only run log of GPT-assisted selections). Stored under home/data or legacy.
- **Config**: `config/taste_profile.yaml`, `settings.json`, etc. Loaded from home/config if home exists or `DAILYDJ_HOME` is set, else legacy repo config.
- **Spotify token cache**: stored under home/.cache if home exists or `DAILYDJ_HOME` is set; otherwise legacy `.cache`.

### Migration
- To keep the repo stateless: create `DAILYDJ_HOME` (default `~/.dailydj`), move `track_history.db`, `config/`, `data/gpt_history.jsonl`, `state/feedback.jsonl`, and `.cache` into it, then set `DAILYDJ_HOME` in your environment. If `DAILYDJ_HOME` is unset and the home does not exist, the code will continue using legacy repo-relative paths.

### Positive feedback (Spotify likes)
- When a user saves/likes a track in Spotify that appeared in a recent DailyDJ run, a `like_track` event is written to `state/feedback.jsonl` (track_uri, artist, timestamp).
- When an artist reaches the like threshold (default 5), a `boost_artist_auto` event is written once for that artist. Learned boosts are applied in scoring (+1.5) but still respect hard bans/cooldowns/per-artist caps.
- Direct liked tracks get an extra scoring bonus (+3.0). No schema changes are required; all signals live in `feedback.jsonl`.
- Reset learned boosts/likes by deleting the relevant lines (or the whole file) in `state/feedback.jsonl`.

## End-to-end flow (daily_dj_refresh.py)
1) Load settings, taste profile, feedback state, mode overrides (e.g., `modes.friday.discovery_ratio`).
2) Determine today’s energy tag (weekday -> tag). Candidate pool query: `tracks WHERE energy_tag = <tag> OR energy_tag IS NULL`; if empty after filtering, fall back to all tracks.
3) Filter candidates: hard bans (including DB artist_bans), no-repeat window, cooldowns, per-artist cap, optional title dedupe, and avoid/banned artists checks.
4) Score candidates (boost/like/avoid weights, scene anchors, discourage list, fatigue penalties/bonuses). Shortlist top 300 by score.
5) GPT (if discovery_ratio > 0): send shortlist URIs, taste profile summary, and constraints. GPT must return JSON `{"picks": ["spotify:track:..."], "notes": "optional"}` using only provided URIs. Invalid or out-of-pool URIs are dropped; if GPT fails or returns none, deterministic ranking is used.
6) Apply constraints to GPT picks, merge with deterministic base, fill to target size/duration, enforce bans/constraints again.
7) Update playlist (replace first 100 URIs, then add remaining in chunks), mark `last_played`, record playlist_run, append feedback `generated` event.
8) Auto-ban removals: tracks manually removed since the last run are banned; if an artist accumulates 3 such track bans, the artist is auto-banned.

## Hard bans and normalization
- Hard bans are enforced before GPT and after GPT merge (`is_hard_banned` in `taste_profile.py`; applied in `gpt_recommender.run_gpt_recommender` and `_apply_artist_rules` in `daily_dj_refresh.py`).
- Normalization lowercases, replaces `&`/`+` with `and`, strips punctuation and extra spaces. Variants like “Florence + The Machine” are caught.
- To unban: remove rows from `bans` and/or `artist_bans` in `track_history.db` (SQLite), or edit the taste profile and clear the DB rows.

## Modes and energy tags
- Day-of-week -> energy tag map is in `daily_dj_refresh.py` (ENERGY_LABELS). The `--energy-tag` flag on `run_gpt_recommender.py` filters the pool by tag but does not change weekday selection.
- Per-mode (e.g., `modes.friday`) overrides discovery ratio and can add boosts/avoids/vibe tags; merged with global lists.
- If the pool for the day’s tag is empty, the refresh falls back to the full catalog.

## Candidate pool and shortlist
- Pool query: `SELECT track_id, artist, title, energy_tag, last_played, duration_ms FROM tracks WHERE energy_tag=? OR energy_tag IS NULL`.
- Required fields for best results: track_id (URI is derived), artist, title; duration_ms helps duration targeting.
- Shortlist size: top 300 by score before GPT; configurable via `candidate_limit` in `run_gpt_recommender` call sites (default 300).

## Feedback loop and source of truth
- Feedback source of truth: `state/feedback.jsonl` (type `generated` events). No feedback is stored in DB.
- Run history source of truth: `playlist_runs` + `playlist_run_tracks` in SQLite; GPT history is also mirrored to `data/gpt_history.jsonl`.
- Fatigue/cooldowns: built from `feedback.jsonl` last-seen timestamps plus DB bans/cooldowns.

## Failure modes and fallbacks
- GPT errors/invalid JSON/out-of-pool URIs: warnings logged; GPT picks dropped; deterministic ranking used to fill.
- Spotify errors (e.g., >100 URIs): playlist updates are chunked; if Spotify fails, the run aborts at that step.
- Empty pool after filtering: falls back to full catalog; if still empty, raises `RuntimeError`.
- OpenAI quota/rate limits: run logs a warning and uses deterministic selection only.
- Auth issues: ensure `.env` has Spotify creds and OpenAI key; scopes used: `playlist-modify-private`, `playlist-read-private`.

## Usage (commands)
- Home directory:
  - Default: `~/.dailydj`. Override with `DAILYDJ_HOME=/path/to/home`.
  - To migrate manually: create the home, move `track_history.db`, `config/`, `data/gpt_history.jsonl`, `state/feedback.jsonl`, and `.cache` into it, then set `DAILYDJ_HOME`.

- Ensure venv and deps installed; `.env` with Spotify and OpenAI keys.
- Migrate DB (once or after schema changes):
  ```
  python3 spotify_automation/migrate_db.py
  ```
- Optional bulk load curated tracks:
  ```
  ./scripts/run_in_venv.sh spotify_automation/bulk_load_tracks.py --input spotify_automation/data/gpt_bulk_tracks.json
  ```
- Run GPT helper without touching playlist:
  ```
  ./scripts/run_in_venv.sh spotify_automation/run_gpt_recommender.py --energy-tag friday --limit 30 --discovery-ratio 0.3
  ```
- Refresh playlist (updates Spotify):
  ```
  ./scripts/run_in_venv.sh spotify_automation/daily_dj_refresh.py
  ```
- Config paths: taste profile `config/taste_profile.yaml`; settings `config/settings.json`; feedback store `state/feedback.jsonl`.

## Troubleshooting
- GPT quota/rate limit: warnings about insufficient_quota; rerun uses deterministic path.
- Empty pool / few tracks: seed more tracks, loosen constraints/cooldowns, or rely on full-catalog fallback.
- URI validation warnings: GPT picked URIs not in shortlist; they are dropped; ensure pool size is sufficient.
- Spotify auth errors: check `.env` creds and scopes; renew token if expired.
- Logs: GPT runs `data/gpt_history.jsonl`; feedback `state/feedback.jsonl`; playlist runs in `track_history.db` tables `playlist_runs` and `playlist_run_tracks`.

## Quickstart for new users
1) Create venv and install deps (example): `python3 -m venv .venv && ./scripts/run_in_venv.sh -m pip install -r requirements.txt`
2) (Optional) Set home: `export DAILYDJ_HOME=~/.dailydj`
3) Bootstrap home with example configs (safe, non-destructive): `./scripts/run_in_venv.sh spotify_automation/init_home.py`
4) Edit your configs under `$DAILYDJ_HOME/config/` (or legacy paths if unset).
5) Run refresh: `./scripts/run_in_venv.sh spotify_automation/daily_dj_refresh.py`
