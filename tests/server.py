# -*- coding: utf-8 -*-

from starlette.applications import Starlette
from midstar.middleware import (
    RateLimitMiddleware,
    EdgeCacheMiddleware,
    ConcurrentRequestMiddleware,
    CacheConfig,
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
    HTTP2PushMiddleware,
    CompressionMiddleware,
    ErrorHandlingMiddleware
)
from midstar.core.backend import InMemoryBackend
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse, JSONResponse
import time

backend = InMemoryBackend()

class NotFoundError(Exception):
    status_code = 404
    def __init__(self, message="Resource not found"):
        self.message = message
        super().__init__(self.message)

class ValidationError(Exception):
    status_code = 422
    def __init__(self, errors=None):
        self.errors = errors or {}
        message = f"Validation failed: {', '.join(self.errors.keys())}"
        super().__init__(message)

def handle_validation_error(exc, scope):
    return {
        "error": {
            "title": "Validation Error",
            "message": str(exc),
            "fields": exc.errors
        }
    }


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
            config = CacheConfig(max_age=60)    
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
        Middleware(
            HTTP2PushMiddleware
        ),
        Middleware(
            CompressionMiddleware,
            minimum_size=1000,
            compressible_content_types=["text/html", "application/json"]
        ),
        Middleware(
            ErrorHandlingMiddleware,
            handlers={
                ValueError: handle_validation_error,
            },
            # log_exceptions=True,
        )
    ]
)

@app.route("/")
def hello(request):
    raise ValidationError({"field1": "Field1 is required", "field2": "Field2 must be a number"})
    return PlainTextResponse("hello")