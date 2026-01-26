"""
Bootstrap script to set up a DailyDJ home directory without touching existing state.

Behavior:
- Home is resolved via DAILYDJ_HOME or defaults to ~/.dailydj (paths.dailydj_home()).
- Creates dirs: home/config, home/state, home/data, home/.cache.
- Copies example configs from spotify_automation/examples/ into home/config if missing.
- Ensures track_history.db exists in home (uses migrate_db/init_db); NEVER overwrites an existing DB.
- Prints actions; --dry-run prints what would happen without changing anything.

Safety:
- Never deletes or overwrites existing files.
- Respects legacy state; does not move files.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from spotify_automation import paths
from spotify_automation import migrate_db

EXAMPLES_DIR = Path(__file__).resolve().parent / "examples"


def copy_if_missing(src: Path, dest: Path, dry_run: bool) -> str:
    if dest.exists():
        return f"skip (exists): {dest}"
    if dry_run:
        return f"would copy: {src} -> {dest}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())
    return f"copied: {src.name} -> {dest}"


def ensure_home(dry_run: bool) -> None:
    home = paths.dailydj_home()
    config = paths.config_dir()
    state = paths.state_dir()
    data = paths.data_dir()
    cache = paths.cache_dir()
    db_path = paths.db_path()

    for dir_path in (home, config, state, data, cache):
        if dry_run:
            print(f"ensure dir (dry-run): {dir_path}")
        else:
            dir_path.mkdir(parents=True, exist_ok=True)

    for fname in ("settings.json", "taste_profile.yaml", "user_profile.json", "rules.json"):
        src = EXAMPLES_DIR / fname
        dest = config / fname
        if src.exists():
            print(copy_if_missing(src, dest, dry_run))

    if db_path.exists():
        print(f"skip DB (exists): {db_path}")
    else:
        if dry_run:
            print(f"would initialize DB at {db_path}")
        else:
            migrate_db.ensure_db_location()
            print(f"initialized DB at {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize DailyDJ home directory safely.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without changes.")
    args = parser.parse_args()
    ensure_home(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
