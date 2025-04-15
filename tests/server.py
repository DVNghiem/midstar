# -*- coding: utf-8 -*-

from starlette.applications import Starlette
from midstar.middleware import (
    RateLimitMiddleware,
    EdgeCacheMiddleware,
    SecurityMiddleware,
    ConcurrentRequestMiddleware
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
        # Middleware(
        #     EdgeCacheMiddleware,
        #     max_age=3600,
        #     s_maxage=None,
        #     stale_while_revalidate=None,
        #     stale_if_error=None,
        #     vary_by=["accept", "accept-encoding"],
        #     cache_control=[],
        #     include_query_string=True,
        #     exclude_paths=["/admin", "/api/private"],
        #     exclude_methods=["POST", "PUT", "DELETE", "PATCH"],
        #     private_paths=[],
        #     cache_by_headers=[],
        # ),
        # Middleware(
        #     SecurityMiddleware,
        #     rate_limiting=True,
        #     jwt_auth=True,
        #     cors_configuration={
        #         "allowed_origins": ["*"],
        #         "allowed_methods": ["GET", "POST", "PUT", "DELETE"],
        #         "max_age": 3600,
        #     },
        #     csrf_protection=True,
        #     security_headers={
        #         "X-Frame-Options": "DENY",
        #         "X-Content-Type-Options": "nosniff",
        #         "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        #     },
        #     jwt_secret="your_jwt_secret",
        #     jwt_algorithm="HS256",
        #     jwt_expires_in=3600,
        # ),
    ]
)

import time
@app.route("/")
def hello(request):
    time.sleep(5)
    return PlainTextResponse("hello")