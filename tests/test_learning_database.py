from pathlib import Path

import pytest

from app import db
from app.learning import store
from app.main import create_app
from app.settings import Settings


def test_learning_store_uses_an_isolated_database_and_prefixed_tables(tmp_path, monkeypatch):
    grounded = tmp_path / "grounded.sqlite3"
    learning = tmp_path / "learning.sqlite3"
    monkeypatch.setenv("NOTEBOOK_DB_PATH", str(grounded))
    monkeypatch.setattr(db, "DB_PATH", learning)

    with store.db() as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}

    assert learning.exists()
    assert not grounded.exists()
    assert tables and all(name.startswith(("learn_", "sqlite_")) for name in tables)


def test_learning_database_refuses_grounded_chat_database(tmp_path, monkeypatch):
    grounded = tmp_path / "same.sqlite3"
    monkeypatch.setenv("NOTEBOOK_DB_PATH", str(grounded))
    monkeypatch.setattr(db, "DB_PATH", grounded)

    with pytest.raises(ValueError, match="separate from NOTEBOOK_DB_PATH"):
        db.connect()
    assert not grounded.exists()


def test_default_learning_database_is_not_the_grounded_chat_database(monkeypatch):
    monkeypatch.delenv("NOTEBOOK_LEARNING_DB_PATH", raising=False)
    monkeypatch.delenv("NOTEBOOK_DB_PATH", raising=False)
    # The module's default is fixed at import time; compare using the same
    # public default grounded-chat setting resolved from the repository root.
    assert Path(db.DB_PATH).resolve() != Path("data/notebook.sqlite3").resolve()


def test_app_factory_rejects_same_explicit_grounded_and_learning_path(tmp_path, monkeypatch):
    shared = tmp_path / "shared.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", shared)

    with pytest.raises(ValueError, match="must use separate paths"):
        create_app(Settings(database_path=shared))
    assert not shared.exists()
