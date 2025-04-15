import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class CacheConfig:
    """
    Configuration class for caching middleware.
    """

    def __init__(
        self,
        max_age: int = 3600,
        s_maxage: Optional[int] = None,
        stale_while_revalidate: Optional[int] = None,
        stale_if_error: Optional[int] = None,
        vary_by: List[str] = None,
        cache_control: List[str] = None,
        include_query_string: bool = True,
        exclude_paths: List[str] = None,
        exclude_methods: List[str] = None,
        private_paths: List[str] = None,
        cache_by_headers: List[str] = None,
        max_cache_size: int = 1000,  # limit the cache etag item
    ):
        self.max_age = max_age
        self.s_maxage = s_maxage
        self.stale_while_revalidate = stale_while_revalidate
        self.stale_if_error = stale_if_error
        self.vary_by = vary_by or ["accept", "accept-encoding"]
        self.cache_control = cache_control or []
        self.include_query_string = include_query_string
        self.exclude_paths = exclude_paths or ["/admin", "/api/private"]
        self.exclude_methods = exclude_methods or ["POST", "PUT", "DELETE", "PATCH"]
        self.private_paths = private_paths or []
        self.cache_by_headers = cache_by_headers or []
        self.max_cache_size = max_cache_size


class EdgeCacheMiddleware:
    """
    Middleware implementing edge caching strategies with support for:
    - Cache-Control directives
    - ETag generation
    - Conditional requests (If-None-Match, If-Modified-Since)
    - Vary header management
    - CDN-specific headers
    """

    def __init__(self, app: ASGIApp, cache_config: CacheConfig | None = None):
        super().__init__()
        self.app = app
        self.cache_config = cache_config or CacheConfig()
        self._etag_cache: Dict[str, tuple[str, str, float]] = {}
        self.request_context = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        if not self._should_cache(request, scope["path"]):
            await self._send_no_cache_response(scope, receive, send)
            return

        cache_key = self._generate_cache_key(request)
        etag_data = self._etag_cache.get(cache_key)
        etag = etag_data[0] if etag_data else None
        last_modified = etag_data[1] if etag_data else None
        timestamp = etag_data[2] if etag_data else None

        if timestamp and (time.time() - timestamp) > self.cache_config.max_age:
            del self._etag_cache[cache_key]
            etag = None
            last_modified = None

        # check conditional request (If-None-Match)
        if etag:
            if_none_match = request.headers.get("if-none-match")
            if if_none_match and if_none_match == etag:
                cache_control = "no-cache, must-revalidate"
                headers = [
                    [b"etag", etag.encode()],
                    [b"cache-control", cache_control.encode()],
                    [b"vary", ", ".join(self.cache_config.vary_by).encode()],
                ]
                if last_modified:
                    headers.append([b"last-modified", last_modified.encode()])
                await send(
                    {
                        "type": "http.response.start",
                        "status": 304,
                        "headers": headers,
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                    }
                )
                return

        # collect and process response
        response_started = False
        response_body = b""
        response_status = 200
        response_headers = []

        async def wrapped_send(event):
            nonlocal \
                response_started, \
                response_body, \
                response_status, \
                response_headers

            if event["type"] == "http.response.start":
                response_started = True
                response_status = event["status"]
                response_headers = event.get("headers", [])

            elif event["type"] == "http.response.body":
                if not response_started:
                    return
                response_body += event.get("body", b"")
                if not event.get("more_body", False):
                    etag = self._generate_etag(response_body)
                    last_modified = datetime.now(tz=timezone.utc).strftime(
                        "%a, %d %b %Y %H:%M:%S GMT"
                    )
                    self._etag_cache[cache_key] = (etag, last_modified, time.time())

                    if len(self._etag_cache) > self.cache_config.max_cache_size:
                        oldest_key = next(
                            iter(self._etag_cache)
                        )  # delete the oldest item
                        del self._etag_cache[oldest_key]

                    cache_control = self._build_cache_control(scope["path"])
                    response_headers.extend(
                        [
                            [b"cache-control", cache_control.encode()],
                            [b"etag", etag.encode()],
                            [b"vary", ", ".join(self.cache_config.vary_by).encode()],
                            [
                                b"last-modified",
                                datetime.now(tz=timezone.utc)
                                .strftime("%a, %d %b %Y %H:%M:%S GMT")
                                .encode(),
                            ],
                            [b"cdn-cache-control", cache_control.encode()],
                            [
                                b"surrogate-control",
                                f"max-age={self.cache_config.s_maxage or self.cache_config.max_age}".encode(),
                            ],
                        ]
                    )
                    await send(
                        {
                            "type": "http.response.start",
                            "status": response_status,
                            "headers": response_headers,
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": response_body,
                            "more_body": False,
                        }
                    )
                    return  # end of response processing beacause we are done

        await self.app(scope, receive, wrapped_send)

    async def _send_no_cache_response(self, scope: Scope, receive: Receive, send: Send):
        """Send response Cache-Control: no-store"""

        async def no_cache_send(event):
            if event["type"] == "http.response.start":
                headers = event.get("headers", [])
                headers.append([b"cache-control", b"no-store"])
                event["headers"] = headers
            await send(event)

        await self.app(scope, receive, no_cache_send)

    def _should_cache(self, request: Request, path: str) -> bool:
        """Check if the request should be cached based on method and path"""
        if request.method.upper() in self.cache_config.exclude_methods:
            return False
        if any(excluded in path for excluded in self.cache_config.exclude_paths):
            return False
        return True

    def _generate_cache_key(self, request: Request) -> str:
        components = [request.method, request.url.path]
        if self.cache_config.include_query_string:
            components.append(str(request.query_params))
        for header in self.cache_config.cache_by_headers:
            value = request.headers.get(header.lower())
            if value:
                components.append(f"{header}:{value}")
        return hashlib.sha256(":".join(components).encode()).hexdigest()

    def _generate_etag(self, body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def _build_cache_control(self, path: str) -> str:
        """Create header Cache-Control"""
        directives = []
        if any(private in path for private in self.cache_config.private_paths):
            directives.append("private")
        else:
            directives.append("public")
        directives.append(f"max-age={self.cache_config.max_age}")
        if self.cache_config.s_maxage is not None:
            directives.append(f"s-maxage={self.cache_config.s_maxage}")
        if self.cache_config.stale_while_revalidate is not None:
            directives.append(
                f"stale-while-revalidate={self.cache_config.stale_while_revalidate}"
            )
        if self.cache_config.stale_if_error is not None:
            directives.append(f"stale-if-error={self.cache_config.stale_if_error}")
        directives.extend(self.cache_config.cache_control)
        return ", ".join(directives)
