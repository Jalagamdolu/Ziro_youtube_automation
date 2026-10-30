import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def load() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return data


def database_url() -> str:
    """Plain libpq URL (PostgresSaver); SQLAlchemy gets the +psycopg variant in db.py."""
    return os.environ["DATABASE_URL"]


def redis_url() -> str:
    return os.environ["REDIS_URL"]


def runs_dir() -> Path:
    return Path(os.environ.get("RUNS_DIR", "runs"))
