"""Exercise the AI boundary and session lifecycle using fictional accounts only."""
from tests.test_learning_backend import learn_client, login, post, workspace
from app.learning import ai, store


def test_student_ai_uses_authorized_context_and_parent_cannot_chat(learn_client, monkeypatch):
    c = learn_client
    csrf, ids, course, lesson, assignment = workspace(c)
    calls = []
    def answer(context, question, history):
        calls.append((context, question, history))
        return {'answer': 'Keep both sides balanced [L1].', 'citations': [{'id': 'L1'}]}
    monkeypatch.setattr(ai, 'answer_question', answer)
    csrf = login(c, 'student')
    result = post(c, '/learn/api/tutor-chat', csrf, course_id=course['id'], lesson_id=lesson['id'], question='Why balance?')
    assert result.status_code == 200
    assert result.json()['answer'].endswith('[L1].')
    ctx, question, history = calls[0]
    assert [item['id'] for item in ctx['lessons']] == [lesson['id']]
    assert set(ctx['student']) == {'id', 'learning_preference'}
    assert history == []
    result = post(c, '/learn/api/tutor-chat', csrf, course_id=course['id'], lesson_id=lesson['id'], question='Another hint?')
    assert result.status_code == 200
    assert calls[-1][2][-1]['role'] == 'assistant'
    csrf = login(c, 'parent')
    assert post(c, '/learn/api/tutor-chat', csrf, course_id=course['id'], lesson_id=lesson['id'], question='Read the student chat').status_code == 403
    assert len(calls) == 2


def test_practice_draft_never_publishes_and_errors_are_safe(learn_client, monkeypatch):
    c = learn_client
    csrf, ids, course, lesson, assignment = workspace(c)
    draft = {'title': 'Small steps', 'instructions': 'Try x+1=3.', 'lesson_content': 'Balance each side.', 'learning_objectives': 'Isolate x.', 'topic': 'equations'}
    monkeypatch.setattr(ai, 'draft_practice', lambda context, request: draft)
    csrf = login(c, 'tutor')
    result = post(c, '/learn/api/practice-drafts', csrf, course_id=course['id'], student_id=ids['student'], topic='equations', request='Use short steps')
    assert result.status_code == 200 and result.json() == draft
    with store.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM learn_assignments').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM learn_lessons').fetchone()[0] == 1
    def fail(*args):
        raise RuntimeError('private endpoint credentials and internal path')
    monkeypatch.setattr(ai, 'draft_practice', fail)
    result = post(c, '/learn/api/practice-drafts', csrf, course_id=course['id'], student_id=ids['student'], topic='equations')
    assert result.status_code == 503
    assert 'private endpoint' not in result.text


def test_logout_invalidates_session_and_expiry_rejects(learn_client):
    c = learn_client
    csrf = login(c, 'student')
    assert post(c, '/learn/api/auth/logout', 'wrong').status_code == 403
    assert post(c, '/learn/api/auth/logout', csrf).status_code == 200
    assert c.get('/learn/api/auth/me').status_code == 401
    login(c, 'student')
    with store.db() as conn:
        conn.execute("UPDATE learn_sessions SET expires_at='2000-01-01T00:00:00+00:00'")
    assert c.get('/learn/api/auth/me').status_code == 401
