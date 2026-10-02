import json
from types import SimpleNamespace

import pytest

from app.learning import ai


@pytest.fixture
def context():
    return {'course': {'title': 'Math'}, 'lessons': [{'id': 7, 'title': 'Fractions',
            'content': 'A fraction describes parts of a whole.', 'learning_objectives': 'Compare parts'}],
            'assignment': {'id': 9, 'title': 'Practice', 'instructions': 'Explain one half.'},
            'student': {'id': 3, 'learning_preference': 'worked_examples'}}


@pytest.fixture
def model(monkeypatch):
    captured = {}
    captured['finish'] = 'stop'
    captured['text'] = 'A fraction describes parts of a whole [L1]. What happens with two equal parts?'
    class Client:
        def __init__(self, **kw):
            captured['client'] = kw
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def create(self, **kw):
            captured['request'] = kw
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason=captured['finish'],
                                   message=SimpleNamespace(content=captured['text']))])
    monkeypatch.setattr(ai, 'OpenAI', Client)
    monkeypatch.setenv('NOTEBOOK_LEARNING_BASE_URL', 'http://127.0.0.1:9999/v1')
    monkeypatch.setenv('NOTEBOOK_LEARNING_MODEL', 'test-model')
    return captured


def test_grounded_scoped_prompt_and_bounded_history(context, model):
    result = ai.answer_question(context, 'Explain a half',
                                [{'role': 'user', 'content': str(n)} for n in range(20)])
    assert result['citations'][0]['lesson_id'] == 7
    assert result['warning'] is None
    assert model['client']['timeout'] == 30
    assert model['client']['max_retries'] == 0
    assert model['request']['max_tokens'] == 768
    messages = model['request']['messages']
    assert len(messages) == 9
    assert 'similar worked example' in messages[0]['content']
    assert 'parts of a whole' in messages[1]['content']
    assert 'username' not in messages[1]['content']


@pytest.mark.parametrize('finish,text', [('length', 'partial'), ('stop', ''), ('tool_calls', 'answer')])
def test_incomplete_output_never_accepted(context, model, finish, text):
    model.update(finish=finish, text=text)
    with pytest.raises(ai.AssistanceUnavailable):
        ai.answer_question(context, 'Explain')


def test_unknown_citations_are_flagged_not_authorized(context, model):
    model['text'] = 'Some explanation [L999].'
    answer = ai.answer_question(context, 'Explain')
    assert answer['citations'] == []
    assert 'unrecognized' in answer['warning']


def test_no_material_abstains_without_model(context, monkeypatch):
    monkeypatch.setattr(ai, '_complete', lambda *a, **k: pytest.fail('must not call model'))
    context.update(lessons=[], assignment=None)
    assert ai.answer_question(context, 'Explain')['citations'] == []


def test_practice_is_an_editable_draft_without_personal_names(context, model):
    model['text'] = json.dumps({'title': 'Equal parts', 'instructions': 'Draw two halves',
                              'lesson_content': 'A half is one of two equal parts.',
                              'learning_objectives': 'Recognize halves', 'topic': 'Fractions'})
    context['student']['display_name'] = 'Private name'
    context['progress'] = {'official': {'percent': 60}, 'topics': []}
    draft = ai.draft_practice(context, 'Use a diagram')
    assert draft['topic'] == 'Fractions'
    assert 'Private name' not in json.dumps(model['request'])
    assert model['request']['max_tokens'] == 1024


def test_malformed_and_duplicate_practice_output_rejected(context, model):
    for value in ['{}', '{"title":"a","title":"b"}', 'NaN', 'not JSON']:
        model['text'] = value
        with pytest.raises(ai.AssistanceUnavailable):
            ai.draft_practice(context)


def test_endpoint_failure_does_not_disclose_details(context, monkeypatch):
    monkeypatch.setenv('NOTEBOOK_LEARNING_BASE_URL', 'http://127.0.0.1:9999/v1')
    monkeypatch.setenv('NOTEBOOK_LEARNING_MODEL', 'test-model')
    def fail(**kw):
        raise RuntimeError('private endpoint with secret')
    monkeypatch.setattr(ai, 'OpenAI', fail)
    with pytest.raises(ai.AssistanceUnavailable) as error:
        ai.answer_question(context, 'Explain')
    assert 'secret' not in str(error.value)


def test_ai_fallback_uses_public_environment_settings(monkeypatch):
    captured = {}
    class Client:
        def __init__(self, **kwargs):
            captured['client'] = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            captured['request'] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason='stop', message=SimpleNamespace(content='ready')
            )])
    monkeypatch.setattr(ai, 'OpenAI', Client)
    for name in ('NOTEBOOK_LEARNING_BASE_URL', 'NOTEBOOK_LEARNING_API_KEY', 'NOTEBOOK_LEARNING_MODEL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('OPENAI_BASE_URL', 'http://127.0.0.1:9998/v1')
    monkeypatch.setenv('OPENAI_API_KEY', 'public-test-key')
    monkeypatch.setenv('OPENAI_MODEL', 'public-test-model')

    assert ai._complete([{'role': 'user', 'content': 'test'}]) == 'ready'
    assert captured['client']['base_url'] == 'http://127.0.0.1:9998/v1'
    assert captured['client']['api_key'] == 'public-test-key'
    assert captured['request']['model'] == 'public-test-model'
