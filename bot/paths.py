"""Filesystem path helpers for the trading bot."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

ROOT_DIR = Path(__file__).resolve().parent.parent
LEGACY_DATA_DIR = ROOT_DIR / "data"


def _iter_candidates() -> Iterator[Path]:
    """Yield potential data directories in priority order."""
    env_values = [os.environ.get("BOT_DATA_DIR"), os.environ.get("BOT_LOG_DIR")]
    for value in env_values:
        if value:
            yield Path(value).expanduser()
    yield Path("/config/bithumb-bot")
    yield Path("/share/bithumb-bot")
    yield Path("/data/bot")
    yield LEGACY_DATA_DIR


def resolve_data_dir() -> Path:
    """Pick the first writable directory from the candidate list."""
    for candidate in _iter_candidates():
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        else:
            return candidate
    # Final fallback: ensure legacy directory exists even if creation failed above.
    LEGACY_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return LEGACY_DATA_DIR


DATA_DIR = resolve_data_dir()

__all__ = ["DATA_DIR", "LEGACY_DATA_DIR", "ROOT_DIR", "resolve_data_dir"]
