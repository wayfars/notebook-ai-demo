from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.settings import Settings


def _settings(tmp_path):
    return Settings(database_path=tmp_path / "notebook.sqlite3")


def test_no_match_abstains_without_calling_model(tmp_path, monkeypatch):
    def unexpected_client(*args, **kwargs):
        raise AssertionError("model should not be called for no-match retrieval")

    monkeypatch.setattr(main, "OpenAI", unexpected_client)
    app = main.create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/ask", json={"question": "Where does the Arctic tern nest?"})
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval"] == "no_match"
    assert "not contain enough information" in body["answer"]
    assert body["sources"] == []


def test_generation_uses_configured_token_bound(tmp_path, monkeypatch):
    calls = {}

    class MockOpenAI:
        def __init__(self, **kwargs): pass
        @property
        def chat(self): return SimpleNamespace(completions=self)
        def create(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="Every 30 days [S1]."), finish_reason="stop"
            )])

    monkeypatch.setattr(main, "OpenAI", MockOpenAI)
    cfg = Settings(database_path=tmp_path / "notebook.sqlite3", max_tokens=320)
    with TestClient(main.create_app(cfg)) as client:
        response = client.post("/api/ask", json={"question": "How often should each HelioDock battery enclosure be inspected?"})
    assert response.status_code == 200
    assert calls["max_tokens"] == 320


def test_reports_unknown_and_missing_citations_and_returns_excerpts(tmp_path, monkeypatch):
    class MockOpenAI:
        def __init__(self, **kwargs):
            pass

        @property
        def chat(self):
            return SimpleNamespace(completions=self)

        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="A made-up answer cites [S9]."), finish_reason="stop"
            )])

    monkeypatch.setattr(main, "OpenAI", MockOpenAI)
    app = main.create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/ask", json={"question": "How often should each HelioDock battery enclosure be inspected?"})
    body = response.json()
    assert response.status_code == 200
    assert body["citation_validation"]["unknown_markers"] == ["S9"]
    assert body["citation_validation"]["missing_citations"] is True
    assert body["citations"] == []
    assert "every 30 days" in body["sources"][0]["excerpt"]


def test_missing_citations_flag_for_non_abstaining_answer(tmp_path, monkeypatch):
    class MockOpenAI:
        def __init__(self, **kwargs): pass
        @property
        def chat(self): return SimpleNamespace(completions=self)
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="The interval is monthly."), finish_reason="stop"
            )])

    monkeypatch.setattr(main, "OpenAI", MockOpenAI)
    with TestClient(main.create_app(_settings(tmp_path))) as client:
        body = client.post("/api/ask", json={"question": "How often should each HelioDock battery enclosure be inspected?"}).json()
    assert body["citation_validation"]["missing_citations"] is True


def test_empty_truncated_and_missing_choice_responses_fail_closed(tmp_path, monkeypatch):
    for choices, message in [([], "no completion choices"),
                             ([SimpleNamespace(message=SimpleNamespace(content=""), finish_reason="stop")], "empty answer"),
                             ([SimpleNamespace(message=SimpleNamespace(content="partial"), finish_reason="length")], "truncated")]:
        class MockOpenAI:
            def __init__(self, **kwargs): pass
            @property
            def chat(self): return SimpleNamespace(completions=self)
            def create(self, **kwargs): return SimpleNamespace(choices=choices)
        monkeypatch.setattr(main, "OpenAI", MockOpenAI)
        with TestClient(main.create_app(_settings(tmp_path))) as client:
            response = client.post("/api/ask", json={"question": "How often should each HelioDock battery enclosure be inspected?"})
        assert response.status_code == 502
        assert message in response.json()["detail"]


def test_filtered_and_unsupported_finishes_fail_closed(tmp_path, monkeypatch):
    for finish_reason in ("content_filter", "tool_calls", "other"):
        class MockOpenAI:
            def __init__(self, **kwargs): pass
            @property
            def chat(self): return SimpleNamespace(completions=self)
            def create(self, **kwargs):
                return SimpleNamespace(choices=[SimpleNamespace(
                    message=SimpleNamespace(content="Every 30 days [S1]."), finish_reason=finish_reason
                )])

        monkeypatch.setattr(main, "OpenAI", MockOpenAI)
        with TestClient(main.create_app(_settings(tmp_path))) as client:
            response = client.post("/api/ask", json={"question": "How often should each HelioDock battery enclosure be inspected?"})
        assert response.status_code == 502


def test_browser_escapes_all_dynamic_content_before_inserting_html():
    script = (Path(__file__).resolve().parents[1] / "static/app.js").read_text()
    assert 'escapeHTML(payload.answer)' in script
    assert 'escapeHTML(s.title)' in script
    assert 'escapeHTML(s.excerpt)' in script
    assert 'validation.unknown_markers.map((marker) => escapeHTML(marker))' in script


def test_flags_malformed_source_markers_as_unknown(tmp_path, monkeypatch):
    class MockOpenAI:
        def __init__(self, **kwargs): pass
        @property
        def chat(self): return SimpleNamespace(completions=self)
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="An answer cites [Sbogus]."), finish_reason="stop"
            )])

    monkeypatch.setattr(main, "OpenAI", MockOpenAI)
    with TestClient(main.create_app(_settings(tmp_path))) as client:
        body = client.post("/api/ask", json={"question": "How often should each HelioDock battery enclosure be inspected?"}).json()
    assert body["citation_validation"]["unknown_markers"] == ["Sbogus"]
