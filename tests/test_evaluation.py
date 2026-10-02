import json
from pathlib import Path

from evaluation.run import run
from app.generation import has_expected_phrase, validate_answer

ROOT = Path(__file__).resolve().parents[1]


def test_offline_evaluation_is_reproducible_and_reports_retrieval_only():
    cases = json.loads((ROOT / "evaluation/cases.json").read_text())
    report = run()
    assert len(cases) == 50
    assert sum(c["answerable"] for c in cases) == 40
    assert report["mode"] == "offline_retrieval_only"
    assert report["metrics"]["sqlite_fts5"]["supporting_source_hit_at_3"] == 1.0
    assert report["metrics"]["shared_word_overlap_baseline"]["supporting_source_hit_at_3"] == 1.0
    assert "No model was called" in report["interpretation"]
    assert "prompt-injection resistance" in report["interpretation"]


def test_live_scoring_helpers_are_explicit_phrase_proxies():
    assert has_expected_phrase("Inspection interval: every 30 days.", ["30 days", "monthly"])
    assert not has_expected_phrase("Inspect regularly.", ["30 days", "monthly"])
    assert validate_answer("The sources do not contain enough information.", "stop", [])["abstained"]
    assert not validate_answer("A 30 day interval is specified.", "stop", [])["abstained"]
