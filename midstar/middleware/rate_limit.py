import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from midstar.core.backend import StorageBackend


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    The RateLimitMiddleware class implements rate limiting functionality to restrict the number of
    Requests per minute for a given IP address.

    The `RateLimitMiddleware` function checks the request rate limit and returns a 429 status code if the
    limit is exceeded.

    """

    def __init__(
        self,
        storage_backend: StorageBackend,
        requests_per_minute=60,
        window_size=60,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.storage = storage_backend
        self.requests_per_minute = requests_per_minute
        self.window_size = window_size

    async def dispatch(self, request, call_next):
        request = self.before_request(request)
        return await super().dispatch(request, call_next)

    def get_request_identifier(self, request: Request):
        return request.client.host

    def before_request(self, request: Request):
        """
        The `before_request` function checks the request rate limit and returns a 429 status code if the
        limit is exceeded.

        :param request: The `request` parameter in the `before_request` method is of type `Request`. It
        is used to represent an incoming HTTP request that the server will process
        :type request: Request
        :return: The code snippet is a method called `before_request` that takes in a `Request` object
        as a parameter.
        """
        identifier = self.get_request_identifier(request)
        current_time = int(time.time())
        window_key = f"{identifier}:{current_time // self.window_size}"

        request_count = self.storage.increment(window_key, expire=self.window_size)

        if request_count > self.requests_per_minute:
            return Response(
                status_code=429,
                content=b"Too Many Requests",
                headers={"Retry-After": str(self.window_size)},
            )

        return request
