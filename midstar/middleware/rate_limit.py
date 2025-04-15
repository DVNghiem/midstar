import time

from starlette.requests import Request
from starlette.responses import Response

from midstar.core.backend import StorageBackend
from starlette.types import ASGIApp, Receive, Scope, Send


class RateLimitMiddleware:
    """
    Rate limiting middleware for restricting the number of requests from a single client.

    This middleware implements a fixed window rate limiting strategy, where requests are
    tracked and limited within specific time windows. It can be used to protect API
    endpoints from abuse, DOS attacks, or to enforce usage limits.

    Examples:
        ```
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            storage_backend=RedisStorageBackend(redis_client),
            requests_per_minute=100,
            window_size=60
        )
        ```

    Attributes:
        app (ASGIApp): The ASGI application instance.
        storage (StorageBackend): Backend for storing rate limit counters.
        requests_per_minute (int): Maximum number of requests allowed per time window.
        window_size (int): Size of the rate limit window in seconds.

    Notes:
        - The middleware identifies clients primarily by their IP address
        - It honors the X-Forwarded-For header for clients behind proxies
        - When rate limit is exceeded, returns a 429 status code with a Retry-After header
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
