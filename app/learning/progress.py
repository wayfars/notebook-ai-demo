"""Descriptive progress from published work, never inferred student ability."""
from collections import defaultdict
from datetime import date
import math


FIELDS = ('course_id', 'course_title', 'assignment_id', 'title', 'topic', 'kind',
          'max_points', 'due_date', 'submitted', 'points', 'published', 'feedback')


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _total(records):
    earned = sum(r['points'] for r in records)
    possible = sum(r['max_points'] for r in records)
    return {'earned': round(earned, 4), 'possible': round(possible, 4),
            'percent': round(100 * earned / possible, 1) if possible else None,
            'graded_count': len(records)}


def summarize(student, records, today=None):
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    safe = []
    graded = {'official': [], 'practice': []}
    topics = defaultdict(list)
    missing = pending = 0
    for original in records:
        r = {k: original.get(k) for k in FIELDS}
        r['submitted'] = bool(r['submitted'])
        r['published'] = bool(r['published'])
        valid = (r['published'] and r['submitted'] and _number(r['points']) and
                 _number(r['max_points']) and r['max_points'] > 0 and
                 0 <= r['points'] <= r['max_points'] and r['kind'] in graded)
        if valid:
            graded[r['kind']].append(r)
            if r['kind'] == 'official':
                topics[r['topic'] or 'General'].append(r)
        else:
            # Draft grades and invalid imported records do not become visible evidence.
            r['points'], r['feedback'] = None, ''
            pending += 1
        if not r['submitted'] and r['due_date']:
            try:
                missing += date.fromisoformat(r['due_date']) < today
            except (ValueError, TypeError):
                pass
        safe.append(r)
    topic_reports = []
    for topic, work in sorted(topics.items()):
        values = _total(work)
        pct = values['percent']
        status = 'excelling' if pct >= 85 else 'needs_attention' if pct < 65 else 'developing'
        topic_reports.append({'topic': topic, **values, 'status': status})
    return {'student': {k: student.get(k) for k in
                        ('id', 'display_name', 'username', 'learning_preference')},
            'official': _total(graded['official']), 'practice': _total(graded['practice']),
            'topics': topic_reports, 'pending_count': pending, 'missing_count': missing,
            'records': safe,
            'interpretation': 'Published official work only: excelling at 85% or above, '
            'needs attention below 65%, developing otherwise. Counts describe evidence; '
            'ungraded work is not zero. Practice is separate. Preferences are adjustable.'}
