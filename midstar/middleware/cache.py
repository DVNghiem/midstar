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
    EdgeCacheMiddleware handles HTTP caching at the edge using ETags.
    This ASGI middleware provides HTTP caching capabilities by implementing 
    ETag-based validation and conditional responses. It manages a local cache
    of ETags for responses and handles conditional requests based on the 
    If-None-Match header.
    The middleware supports configurable cache control directives, cache key
    generation based on various request attributes, and selective caching
    based on request method and path patterns.
    Features:
    - In-memory ETag caching with configurable size limits and TTL
    - Conditional responses (304 Not Modified) for unchanged content
    - Fine-grained cache control header management
    - Support for private/public cache directives based on URL paths
    - Cache key generation based on request attributes
    - Cache exclusion for specific paths and HTTP methods
        ```python
        app = FastAPI()
        cache_config = CacheConfig(
            max_age=300,  # 5 minutes
            s_maxage=600,  # 10 minutes for CDNs
            private_paths=["/user/", "/account/"],
            exclude_paths=["/admin/"],
            vary_by=["Accept", "Accept-Encoding"]
        app.add_middleware(EdgeCacheMiddleware, config=cache_config)
        ```
    """
    def __init__(self, app: ASGIApp, config: CacheConfig | None = None):
        super().__init__()
        self.app = app
        self.config = config or CacheConfig()
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

        if timestamp and (time.time() - timestamp) > self.config.max_age:
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
                    [b"vary", ", ".join(self.config.vary_by).encode()],
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

                    if len(self._etag_cache) > self.config.max_cache_size:
                        oldest_key = next(
                            iter(self._etag_cache)
                        )  # delete the oldest item
                        del self._etag_cache[oldest_key]

                    cache_control = self._build_cache_control(scope["path"])
                    response_headers.extend(
                        [
                            [b"cache-control", cache_control.encode()],
                            [b"etag", etag.encode()],
                            [b"vary", ", ".join(self.config.vary_by).encode()],
                            [
                                b"last-modified",
                                datetime.now(tz=timezone.utc)
                                .strftime("%a, %d %b %Y %H:%M:%S GMT")
                                .encode(),
                            ],
                            [b"cdn-cache-control", cache_control.encode()],
                            [
                                b"surrogate-control",
                                f"max-age={self.config.s_maxage or self.config.max_age}".encode(),
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
        """
        Send the response with cache-control: no-store header.

        This method wraps the original send function to inject a cache-control header
        that prevents responses from being stored in any cache.

        Parameters:
        -----------
        scope : Scope
            The ASGI connection scope.
        receive : Receive
            The ASGI receive channel, a callable that will yield a new event when one is available.
        send : Send
            The ASGI send channel, a callable that accepts events to send back to the client.

        Returns:
        --------
        None
        """

        async def no_cache_send(event):
            if event["type"] == "http.response.start":
                headers = event.get("headers", [])
                headers.append([b"cache-control", b"no-store"])
                event["headers"] = headers
            await send(event)

        await self.app(scope, receive, no_cache_send)

    def _should_cache(self, request: Request, path: str) -> bool:
        """Check if the request should be cached based on method and path"""
        if request.method.upper() in self.config.exclude_methods:
            return False
        if any(excluded in path for excluded in self.config.exclude_paths):
            return False
        return True

    def _generate_cache_key(self, request: Request) -> str:
        """
        Generate a unique cache key based on the request attributes.
        
        The key is generated from a combination of:
        - Request method (e.g., GET, POST)
        - Request URL path
        - Query parameters (if include_query_string is enabled in config)
        - Selected headers (as specified in config.cache_by_headers)
        
        The combined components are joined with colons, hashed using SHA-256,
        and returned as a hexadecimal string.
        
        Args:
            request (Request): The FastAPI request object for which to generate a cache key
            
        Returns:
            str: A SHA-256 hash hexadecimal string that serves as the cache key
        """
        components = [request.method, request.url.path]
        if self.config.include_query_string:
            components.append(str(request.query_params))
        for header in self.config.cache_by_headers:
            value = request.headers.get(header.lower())
            if value:
                components.append(f"{header}:{value}")
        return hashlib.sha256(":".join(components).encode()).hexdigest()

    def _generate_etag(self, body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def _build_cache_control(self, path: str) -> str:
        """
        Builds a Cache-Control header value based on the configuration settings and the request path.
        
        This method constructs a Cache-Control header string by combining various cache directives
        according to the middleware configuration. It determines whether the resource should be
        considered private or public based on the path, and adds caching duration parameters
        like max-age, s-maxage, stale-while-revalidate, and stale-if-error when configured.
        
        Args:
            path: The request path to determine appropriate cache directives
            
        Returns:
            A string containing comma-separated Cache-Control directives
            
        Example:
            When path is "/api/private/data" might return:
            "private, max-age=300, s-maxage=600, stale-while-revalidate=60"
        """
        directives = []
        if any(private in path for private in self.config.private_paths):
            directives.append("private")
        else:
            directives.append("public")
        directives.append(f"max-age={self.config.max_age}")
        if self.config.s_maxage is not None:
            directives.append(f"s-maxage={self.config.s_maxage}")
        if self.config.stale_while_revalidate is not None:
            directives.append(
                f"stale-while-revalidate={self.config.stale_while_revalidate}"
            )
        if self.config.stale_if_error is not None:
            directives.append(f"stale-if-error={self.config.stale_if_error}")
        directives.extend(self.config.cache_control)
        return ", ".join(directives)
