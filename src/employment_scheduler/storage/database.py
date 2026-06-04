"""SQLite connection helpers."""

from __future__ import annotations

from pathlib import Path
import sqlite3


DEFAULT_DB_PATH = Path("data/employment.sqlite")


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
