from app.learning.progress import summarize


def record(**overrides):
    return {'kind': 'official', 'topic': 'Fractions', 'submitted': True,
            'published': True, 'points': 8, 'max_points': 10, 'feedback': 'Keep going',
            'due_date': None, **overrides}


def test_weighted_official_and_separate_practice():
    report = summarize({'id': 1, 'password_hash': 'never expose'},
                       [record(), record(points=90, max_points=100),
                        record(kind='practice', points=1)])
    assert report['official']['percent'] == 89.1
    assert report['practice']['percent'] == 10
    assert report['topics'][0]['status'] == 'excelling'
    assert report['topics'][0]['graded_count'] == 2
    assert 'password_hash' not in report['student']


def test_draft_grade_hidden_and_pending_is_not_zero():
    report = summarize({}, [record(published=False, points=2, feedback='private draft')])
    assert report['official']['percent'] is None
    assert report['records'][0]['points'] is None
    assert report['records'][0]['feedback'] == ''
    assert report['pending_count'] == 1
    assert report['topics'] == []


def test_overdue_unsubmitted_and_invalid_grades_are_not_evidence():
    rows = [record(submitted=False, points=None, due_date='2026-01-01'),
            record(points=float('nan')), record(points=True), record(points=11),
            record(max_points=0), record(due_date='invalid')]
    report = summarize({}, rows, today='2026-01-02')
    assert report['missing_count'] == 1
    assert report['official']['graded_count'] == 1
    assert report['official']['percent'] == 80
    assert report['pending_count'] == 5


def test_zero_is_a_valid_published_score_and_no_records_is_unknown():
    assert summarize({}, [record(points=0)])['topics'][0]['status'] == 'needs_attention'
    assert summarize({}, [])['official']['percent'] is None
