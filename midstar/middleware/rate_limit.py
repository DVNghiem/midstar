import time

from starlette.requests import Request
from starlette.responses import Response

from midstar.core.backend import StorageBackend
from starlette.types import ASGIApp, Receive, Scope, Send


class RateLimitMiddleware:
    """
    The RateLimitMiddleware class implements rate limiting functionality to restrict the number of
    Requests per minute for a given IP address.

    The `RateLimitMiddleware` function checks the request rate limit and returns a 429 status code if the
    limit is exceeded.

    """

    def __init__(
        self,
        app: ASGIApp,
        storage_backend: StorageBackend,
        requests_per_minute=60,
        window_size=60,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.app = app
        self.storage = storage_backend
        self.requests_per_minute = requests_per_minute
        self.window_size = window_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ["http", "websocket"]:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        identifier = self.get_request_identifier(request)
        current_time = int(time.time())
        window_key = f"{identifier}:{current_time // self.window_size}"
        request_count = self.storage.increment(window_key, expire=self.window_size)

        if request_count > self.requests_per_minute:
            await Response(
                status_code=429,
                content=b"Too Many Requests",
                headers={"Retry-After": str(self.window_size)},
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def get_request_identifier(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        return forwarded.split(",")[0].strip() if forwarded else request.client.host
