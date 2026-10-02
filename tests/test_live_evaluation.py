from types import SimpleNamespace

from app.generation import validate_answer
from app.settings import Settings
from evaluation import run_live


def _patch_settings(monkeypatch, database_path):
    settings = Settings(database_path=database_path)
    monkeypatch.setattr(run_live, "Settings", SimpleNamespace(from_env=lambda: settings))


def _client_class(answer="Inspection interval: every 30 days [S1].", finish_reason="stop",
                  failure=None):
    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=self)

        def create(self, **kwargs):
            if failure:
                raise failure
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=answer), finish_reason=finish_reason)],
                usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10, total_tokens=30),
            )

    return FakeClient


def test_live_errors_are_per_case_counted_and_do_not_touch_app_database(tmp_path, monkeypatch):
    configured_db = tmp_path / "should-not-be-created.sqlite3"
    _patch_settings(monkeypatch, configured_db)
    monkeypatch.setattr(run_live, "OpenAI", _client_class(failure=RuntimeError("secret endpoint details")))

    report = run_live.run_live(limit=2)

    assert report["case_count"] == 2
    assert report["limited_run"] is True
    assert report["metrics"]["endpoint_errors"] == 2
    assert report["metrics"]["answer_phrase_check_rate_answerable"] == 0
    assert all(case["status"] == "error" for case in report["cases"])
    assert all("secret" not in str(case["error"]) for case in report["cases"])
    assert not configured_db.exists()


def test_markerless_completed_answer_fails_integrity_and_acceptance(tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path / "configured.sqlite3")
    monkeypatch.setattr(run_live, "OpenAI", _client_class(answer="Inspection interval: every 30 days."))

    report = run_live.run_live(limit=1)

    result = report["cases"][0]
    assert result["status"] == "completed"
    assert result["answer_phrase_check"] is True
    assert result["citation_marker_integrity"] is False
    assert result["cites_expected_source"] is False
    assert result["answer_accepted"] is False
    assert report["metrics"]["citation_marker_integrity_rate_answerable"] == 0
    assert result["usage"] == {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}


def test_truncated_or_filtered_answer_never_passes_answer_checks(tmp_path, monkeypatch):
    _patch_settings(monkeypatch, tmp_path / "configured.sqlite3")
    monkeypatch.setattr(run_live, "OpenAI", _client_class(
        answer="Inspection interval: every 30 days [S1].", finish_reason="length"))

    report = run_live.run_live(limit=1)

    result = report["cases"][0]
    assert result["status"] == "truncated"
    assert result["answer_phrase_check"] is False
    assert result["citation_marker_integrity"] is False
    assert result["answer_accepted"] is False
    assert report["metrics"]["non_completed_model_answers"] == 1


def test_shared_validation_requires_stop_and_a_known_marker():
    citations = [{"marker": "S1", "source_id": "ops"}]
    assert validate_answer("Every 30 days [S1].", "stop", citations)["complete"] is True
    assert validate_answer("Every 30 days [S1].", "content_filter", citations)["complete"] is False
    assert validate_answer("Every 30 days [S9].", "stop", citations)["citation_marker_integrity"] is False
    assert validate_answer("Every 30 days", "stop", citations)["citation_marker_integrity"] is False
