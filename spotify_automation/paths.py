from __future__ import annotations

import os
from pathlib import Path


def dailydj_home() -> Path:
    env = os.environ.get("DAILYDJ_HOME")
    if env:
        return Path(env).expanduser()
    return Path("~/.dailydj").expanduser()


def _legacy_root() -> Path:
    return Path(__file__).resolve().parent


def config_dir() -> Path:
    home = dailydj_home()
    legacy = _legacy_root() / "config"
    if os.environ.get("DAILYDJ_HOME"):
        return home / "config"
    if legacy.exists():
        return legacy
    if (home / "config").exists():
        return home / "config"
    return home / "config"


def data_dir() -> Path:
    home = dailydj_home()
    legacy = _legacy_root() / "data"
    if os.environ.get("DAILYDJ_HOME"):
        return home / "data"
    if legacy.exists():
        return legacy
    if (home / "data").exists():
        return home / "data"
    return home / "data"


def state_dir() -> Path:
    home = dailydj_home()
    legacy = _legacy_root() / "state"
    if os.environ.get("DAILYDJ_HOME"):
        return home / "state"
    if legacy.exists():
        return legacy
    if (home / "state").exists():
        return home / "state"
    return home / "state"


def cache_dir() -> Path:
    home = dailydj_home()
    legacy = Path(__file__).resolve().parent / ".cache"
    if os.environ.get("DAILYDJ_HOME"):
        return home / ".cache"
    if legacy.exists():
        return legacy
    if (home / ".cache").exists():
        return home / ".cache"
    return home / ".cache"


def db_path() -> Path:
    home_db = dailydj_home() / "track_history.db"
    legacy_db = _legacy_root() / "track_history.db"
    if os.environ.get("DAILYDJ_HOME"):
        return home_db
    if legacy_db.exists():
        return legacy_db
    if home_db.exists():
        return home_db
    return home_db
