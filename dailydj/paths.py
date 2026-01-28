from __future__ import annotations

import os
from pathlib import Path

from spotify_automation import paths as engine_paths

# Re-export engine path helpers so the CLI can resolve paths consistently.


def set_home(path: Path | None) -> None:
    if path:
        os.environ["DAILYDJ_HOME"] = str(path.expanduser())


def dailydj_home() -> Path:
    return engine_paths.dailydj_home()


def config_dir() -> Path:
    return engine_paths.config_dir()


def data_dir() -> Path:
    return engine_paths.data_dir()


def state_dir() -> Path:
    return engine_paths.state_dir()


def cache_dir() -> Path:
    return engine_paths.cache_dir()


def db_path() -> Path:
    return engine_paths.db_path()
