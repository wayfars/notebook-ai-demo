import asyncio
from app.learning.limits import LearningBodyLimit


def test_chunked_body_rejected_before_application():
    called = []
    sent = []
    events = iter([{'type': 'http.request', 'body': b'123', 'more_body': True},
                   {'type': 'http.request', 'body': b'456', 'more_body': False}])
    async def app(scope, receive, send):
        called.append(True)
    async def receive():
        return next(events)
    async def send(event):
        sent.append(event)
    asyncio.run(LearningBodyLimit(app, max_bytes=5)(
        {'type': 'http', 'path': '/learn/api/tutor-chat', 'method': 'POST'}, receive, send))
    assert not called
    assert sent[0]['status'] == 413


def test_valid_chunks_preserved():
    events = [{'type': 'http.request', 'body': b'12', 'more_body': True},
              {'type': 'http.request', 'body': b'3', 'more_body': False}]
    original = iter(events)
    received = []
    async def receive():
        return next(original)
    async def app(scope, receive, send):
        received.extend([await receive(), await receive()])
    async def send(event):
        pass
    asyncio.run(LearningBodyLimit(app, max_bytes=5)(
        {'type': 'http', 'path': '/learn/api/profile', 'method': 'POST'}, receive, send))
    assert received == events
