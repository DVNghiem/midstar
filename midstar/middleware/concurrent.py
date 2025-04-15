import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send


class ConcurrentRequestMiddleware:
    # The `ConcurrentRequestMiddleware` class limits the number of concurrent requests and returns a 429
    # status code with a Retry-After header if the limit is reached.
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
