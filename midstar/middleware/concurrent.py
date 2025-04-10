from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class ConcurrentRequestMiddleware(BaseHTTPMiddleware):
    # The `ConcurrentRequestMiddleware` class limits the number of concurrent requests and returns a 429
    # status code with a Retry-After header if the limit is reached.
    def __init__(self, max_concurrent_requests=100):
        super().__init__()
        self.max_concurrent_requests = max_concurrent_requests
        self.current_requests = 0
        self.lock = Lock()

    async def dispatch(self, request, call_next):
        """
        The `before_request` function limits the number of concurrent requests and returns a 429 status code
        with a Retry-After header if the limit is reached.

        :param request: The `before_request` method in the code snippet is a method that is called before
        processing each incoming request. It checks if the number of current requests is within the allowed
        limit (`max_concurrent_requests`). If the limit is exceeded, it returns a 429 status code with a
        "Too Many Requests
        :return: the `request` object after checking if the number of current requests is within the allowed
        limit. If the limit is exceeded, it returns a 429 status code response with a "Too Many Requests"
        description and a "Retry-After" header set to 5.
        """

        with self.lock:
            if self.current_requests >= self.max_concurrent_requests:
                return Response(
                    status_code=429,
                    description="Too Many Requests",
                    headers={"Retry-After": "5"},
                )
            self.current_requests += 1
        response = await super().dispatch(request, call_next)
        with self.lock:
            self.current_requests -= 1
        return response
