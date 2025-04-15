import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send


class ConcurrentRequestMiddleware:
    """A middleware for ASGI applications that limits the number of concurrent requests.

    This middleware tracks the number of active requests and rejects new requests with a
    429 "Too Many Requests" response when the concurrent request limit is exceeded.

    Parameters
    ----------
    app : ASGIApp
        The ASGI application that this middleware wraps.
    max_concurrent_requests : int, default=100
        The maximum number of concurrent requests allowed. Requests exceeding this limit
        will receive a 429 response.

    Attributes
    ----------
    app : ASGIApp
        The wrapped ASGI application.
    max_concurrent_requests : int
        The maximum number of concurrent requests allowed.
    current_requests : int
        The current number of active requests being processed.
    lock : asyncio.Lock
        A lock used to synchronize access to the request counter.

    Notes
    -----
    This middleware only applies to HTTP requests. Other ASGI protocol types
    (like WebSocket) are passed through without counting against the limit."""

    def __init__(self, app: ASGIApp, max_concurrent_requests=100):
        super().__init__()
        self.app = app
        self.max_concurrent_requests = max_concurrent_requests
        self.current_requests = 0
        self.lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """
        The `__call__` method is the entry point for the middleware. It checks if the number of current
        requests is within the allowed limit (`max_concurrent_requests`). If the limit is exceeded, it
        returns a 429 status code with a "Too Many Requests" description.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        async with self.lock:
            if self.current_requests >= self.max_concurrent_requests:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [[b"content-type", b"text/plain"]],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"Too Many Requests",
                    }
                )
                return
            self.current_requests += 1
        await self.app(scope, receive, send)
        async with self.lock:
            self.current_requests -= 1
