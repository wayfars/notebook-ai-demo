"""Focused tests for the standalone authenticated learning UI shell."""

from pathlib import Path
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.learning.web import router
from app.web import ROOT


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_learning_shell_is_standalone_and_loads_versioned_assets():
    with _client() as client:
        response = client.get("/learn/")
        login = client.get("/learn/login")

    assert response.status_code == 200
    assert login.status_code == 200
    assert 'data-focus-login="false"' in response.text
    assert 'data-focus-login="true"' in login.text
    assert 'href="/static/features/learning.css?v=' in response.text
    assert 'src="/static/features/learning.js?v=' in response.text
    assert "base.html" not in response.text
    assert "role picker" in response.text.lower()
    assert 'id="login-form"' in response.text
    assert 'id="workspace-view"' in response.text


def test_learning_ui_covers_role_workflows_and_uses_text_only_dynamic_rendering():
    script = (ROOT / "static/features/learning.js").read_text()
    styles = (ROOT / "static/features/learning.css").read_text()
    template = (ROOT / "templates/learning/index.html").read_text()

    for endpoint in (
        "/auth/login", "/auth/logout", "/auth/me", "/dashboard", "/directory",
        "/users", "/parent-links", "/courses", "/enrollments", "/tutors",
        "/lessons", "/assignments", "/submissions", "/grade", "/students/",
        "/profile", "/tutor-chat", "/practice-drafts",
    ):
        assert endpoint in script
    for role_section in (
        "renderTeacherCourses", "renderPeople", "renderStudentLearning", "renderPreference",
        "renderChildren", "renderTutorLearners", "renderPractice", "renderPracticeEditor", "renderSubmissions",
    ):
        assert role_section in script

    assert "textContent" in script
    assert not re.search(r"\.innerHTML\b|insertAdjacentHTML|document\.write\s*\(|\beval\s*\(", script)
    assert "csrf_token" in script and "X-CSRF-Token" in script
    assert "without a published grade" in script
    assert "replaceAll('_', ' ')" in script
    assert "Start a manual draft" in script
    assert "lesson_content: '', learning_objectives: ''" in script
    assert "const editorCourseId = String(state.courseId);" in script
    assert "let practiceLessonId = null;" in script
    assert ".grid > .card:not([class*=\"span-\"]) { grid-column: span 12; }" in styles
    assert "maxlength" in template.lower()
    assert "aria-live" in template.lower()
