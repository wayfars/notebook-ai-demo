"""Bound JSON bodies before FastAPI parsing, including chunked uploads."""
from starlette.responses import JSONResponse


class LearningBodyLimit:
    def __init__(self, app, max_bytes=100_000):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope.get('path', '').startswith('/learn/api/') or scope.get('method') not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        chunks = []
        size = 0
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect':
                return
            size += len(event.get('body', b''))
            if size > self.max_bytes:
                return await JSONResponse({'detail': 'request body too large'}, status_code=413)(scope, receive, send)
            chunks.append(event)
            if not event.get('more_body', False):
                break
        index = 0
        async def bounded_receive():
            nonlocal index
            if index < len(chunks):
                event = chunks[index]
                index += 1
                return event
            return await receive()
        await self.app(scope, bounded_receive, send)
