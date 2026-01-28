from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dailydj import paths as cli_paths
from spotify_automation import init_home, daily_dj_refresh


def _set_home(home: str | None) -> None:
    if home:
        os.environ["DAILYDJ_HOME"] = str(Path(home).expanduser())


def cmd_init(args: argparse.Namespace) -> int:
    _set_home(args.home)
    init_home.ensure_home(dry_run=args.dry_run)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    _set_home(args.home)
    daily_dj_refresh.main()
    return 0


def _redact(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return value[:2] + "***" + value[-2:]


def cmd_doctor(args: argparse.Namespace) -> int:
    _set_home(args.home)
    config_dir = cli_paths.config_dir()
    state_dir = cli_paths.state_dir()
    data_dir = cli_paths.data_dir()
    cache_dir = cli_paths.cache_dir()
    db_path = cli_paths.db_path()

    missing = []
    print(f"Home: {cli_paths.dailydj_home()}")
    print(f"Config: {config_dir} (settings.json, taste_profile.yaml)")
    print(f"State: {state_dir}")
    print(f"Data: {data_dir}")
    print(f"Cache: {cache_dir}")
    print(f"DB: {db_path}")

    if not (config_dir / "settings.json").exists():
        missing.append("settings.json")
    if not (config_dir / "taste_profile.yaml").exists():
        missing.append("taste_profile.yaml")
    if not db_path.exists():
        # do not create here; just warn
        missing.append("track_history.db")

    spotify_env = {
        "SPOTIPY_CLIENT_ID": os.environ.get("SPOTIPY_CLIENT_ID"),
        "SPOTIPY_CLIENT_SECRET": os.environ.get("SPOTIPY_CLIENT_SECRET"),
        "SPOTIPY_REDIRECT_URI": os.environ.get("SPOTIPY_REDIRECT_URI"),
    }
    openai_key = os.environ.get("OPENAI_API_KEY")

    print("Env:")
    for key, val in spotify_env.items():
        status = "set" if val else "missing"
        print(f"  {key}: {status} ({_redact(val or '')})")
    print(f"  OPENAI_API_KEY: {'set' if openai_key else 'missing'} ({_redact(openai_key or '')})")

    if missing:
        print(f"Missing critical files: {', '.join(missing)}")
        return 1
    return 0


def cmd_print_config(args: argparse.Namespace) -> int:
    _set_home(args.home)
    config_dir = cli_paths.config_dir()
    state_dir = cli_paths.state_dir()
    data_dir = cli_paths.data_dir()
    cache_dir = cli_paths.cache_dir()
    db_path = cli_paths.db_path()
    settings = {}
    taste = {}
    settings_path = config_dir / "settings.json"
    taste_path = config_dir / "taste_profile.yaml"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except Exception:
            settings = {"error": "could not parse settings.json"}
    if taste_path.exists():
        try:
            import yaml
            taste = yaml.safe_load(taste_path.read_text()) or {}
        except Exception:
            taste = {"error": "could not parse taste_profile.yaml"}

    print("Paths:")
    print(f"  home: {cli_paths.dailydj_home()}")
    print(f"  config: {config_dir}")
    print(f"  state: {state_dir}")
    print(f"  data: {data_dir}")
    print(f"  cache: {cache_dir}")
    print(f"  db: {db_path}")
    print("Settings (redacted where applicable):")
    sanitized = settings.copy()
    for key in ("openai_api_key", "spotify_client_id", "spotify_client_secret"):
        if key in sanitized:
            sanitized[key] = "***"
    print(json.dumps(sanitized, indent=2))
    print("Taste profile summary:")
    print(json.dumps({k: v for k, v in taste.items() if k in ("hard_bans", "avoid", "boost", "like", "constraints", "modes")}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="DailyDJ CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize DailyDJ home directory.")
    p_init.add_argument("--home", help="Override DAILYDJ_HOME for this command.")
    p_init.add_argument("--dry-run", action="store_true", help="Print actions without changes.")
    p_init.set_defaults(func=cmd_init)

    p_run = sub.add_parser("run", help="Run the DailyDJ refresh.")
    p_run.add_argument("--home", help="Override DAILYDJ_HOME for this command.")
    p_run.set_defaults(func=cmd_run)

    p_doc = sub.add_parser("doctor", help="Check environment and required files.")
    p_doc.add_argument("--home", help="Override DAILYDJ_HOME for this command.")
    p_doc.set_defaults(func=cmd_doctor)

    p_print = sub.add_parser("print-config", help="Print resolved config and paths.")
    p_print.add_argument("--home", help="Override DAILYDJ_HOME for this command.")
    p_print.set_defaults(func=cmd_print_config)

    args = parser.parse_args(argv)
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
