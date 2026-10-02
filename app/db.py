"""Isolated SQLite connection for the authenticated learning workspace.

The learning module deliberately uses a different database from the grounded
chat demo. Set NOTEBOOK_LEARNING_DB_PATH to choose its location. The default is
under the user's XDG data directory and never creates learning tables in the
grounded-chat database.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def _default_path() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser()
    if not data_home.is_absolute():
        data_home = Path.home() / data_home
    return data_home / "notebook-learning" / "learning.sqlite3"


DB_PATH = Path(os.environ.get("NOTEBOOK_LEARNING_DB_PATH", str(_default_path()))).expanduser()


def _ensure_isolated(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    grounded_path = Path(os.environ.get("NOTEBOOK_DB_PATH", "data/notebook.sqlite3")).expanduser().resolve()
    if resolved == grounded_path:
        raise ValueError("learning database must be separate from NOTEBOOK_DB_PATH")
    return resolved


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Connect only to the separate learning database, enabling FK checks."""
    target = _ensure_isolated(Path(path) if path is not None else DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
