# -*- coding: utf-8 -*-

from starlette.applications import Starlette
from midstar.middleware import (
    RateLimitMiddleware,
    EdgeCacheMiddleware,
    ConcurrentRequestMiddleware,
    CacheConfig,
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
)
from midstar.core.backend import InMemoryBackend
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
backend = InMemoryBackend()

app = Starlette(
    middleware=[
        Middleware(
            ConcurrentRequestMiddleware,
            max_concurrent_requests=1,
        ),
        Middleware(
            RateLimitMiddleware,
            storage_backend=backend,
            requests_per_minute=1,
            window_size=1
        ),
        Middleware(
            EdgeCacheMiddleware,
            cache_config = CacheConfig(max_age=60)    
        ),
        Middleware(
            SecurityHeadersMiddleware,
            config=SecurityHeadersConfig(
                headers={
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Content-Security-Policy": "default-src 'self'",
                }
            ),
        ),
    ]
)

import time
@app.route("/")
def hello(request):
    # time.sleep(5)
    return PlainTextResponse("hello")