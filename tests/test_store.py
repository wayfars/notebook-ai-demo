import json
import math
from pathlib import Path

from app.store import connect, retrieve_fts, retrieve_overlap, seed_documents
from app.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_retrievers_find_expected_support_and_ignore_query_stopwords(tmp_path):
    docs = json.loads((ROOT / "data/sample_sources.json").read_text())
    with connect(tmp_path / "store.sqlite3") as conn:
        seed_documents(conn, docs)
        question = "What is the reserved host name assigned to the gateway?"
        assert retrieve_fts(conn, question)[0]["id"] == "network"
        assert retrieve_overlap(docs, question)[0]["id"] == "network"
        assert retrieve_fts(conn, "Where does the Arctic tern nest?") == []


def test_reindex_replaces_existing_source_text(tmp_path):
    with connect(tmp_path / "store.sqlite3") as conn:
        seed_documents(conn, [{"id": "x", "title": "Old", "body": "obsolete token"}])
        seed_documents(conn, [{"id": "x", "title": "New", "body": "current material"}])
        assert retrieve_fts(conn, "obsolete token") == []
        assert retrieve_fts(conn, "current material")[0]["title"] == "New"




def test_settings_require_finite_positive_timeout_nonempty_model_and_bounded_tokens(tmp_path):
    for timeout in (0, -1, math.inf, math.nan):
        try:
            Settings(database_path=tmp_path / "db.sqlite3", timeout_seconds=timeout)
        except ValueError as exc:
            assert "finite and positive" in str(exc)
        else:
            raise AssertionError(f"timeout {timeout!r} should be rejected")
    for model, max_tokens in (("   ", 512), ("model", 0), ("model", 4097)):
        try:
            Settings(database_path=tmp_path / "db.sqlite3", model=model, max_tokens=max_tokens)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid model/token configuration should be rejected")
