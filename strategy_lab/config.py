"""Project-wide paths and settings.

Everything that touches the filesystem goes through these paths so tests can point them at a
temp dir via the ``STRATEGY_LAB_DATA_DIR`` environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    return Path(os.environ.get("STRATEGY_LAB_DATA_DIR", PROJECT_ROOT / "data"))


def raw_dir() -> Path:
    """Downloaded source files (zips, CSVs, JSON pages), one sub-folder per source."""
    return data_dir() / "raw"


def bars_dir() -> Path:
    """Canonical 1m bars: ``bars/source=<s>/symbol=<sym>/year=<y>/part-0.parquet``."""
    return data_dir() / "bars"


def funding_dir() -> Path:
    return data_dir() / "funding"


def resampled_dir() -> Path:
    return data_dir() / "resampled"


def reports_dir() -> Path:
    return data_dir()


def state_db_path() -> Path:
    """SQLite file for results, jobs and LLM cost logs."""
    return data_dir() / "strategy_lab.sqlite"
