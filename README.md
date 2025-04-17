# Midstar
Midstar is a collection of middleware components for ASGI applications (like FastAPI and Starlette) that provides essential security features, performance optimizations, and utility functions to enhance your web applications.

Installation

```sh
pip install midstar
```
## Key Features
- Security: CSRF protection, JWT authentication, and customizable security headers
- Performance: HTTP caching with ETag support, rate limiting, and concurrent request limiting
- Simple Configuration: Easy-to-use configuration objects for each middleware component

### Middleware Components
Security Middleware

#### SecurityHeadersMiddleware
Adds essential security headers to HTTP responses to protect against common web vulnerabilities.
```python
from starlette.applications import Starlette
from midstar.middleware import SecurityHeadersMiddleware, SecurityHeadersConfig

config = SecurityHeadersConfig(
    headers={
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'self'"
    }
)
app = Starlette()
app.add_middleware(SecurityHeadersMiddleware, config=config)
```

#### CSRFProtectionMiddleware
Provides Cross-Site Request Forgery (CSRF) protection for your application.

```python
from midstar.middleware import CSRFProtectionMiddleware, CSRFConfig

app.add_middleware(
    CSRFProtectionMiddleware, 
    config=CSRFConfig(
        secret_key=b"your-secret-key",
        token_lifetime=3600  # 1 hour
    )
)
```
#### JWTMiddleware
Handles JWT-based authentication for protected routes.
```python
from midstar.middleware import JWTMiddleware

app.add_middleware(
    JWTMiddleware,
    jwt_secret="your-secret-key",
    jwt_algorithm="HS256",
    jwt_expires_in=3600
)
```
### Performance Middleware
#### EdgeCacheMiddleware
Implements HTTP caching using ETags to reduce bandwidth and improve response times.
```python
from midstar.middleware import EdgeCacheMiddleware, CacheConfig

cache_config = CacheConfig(
    max_age=300,  # 5 minutes
    s_maxage=600,  # 10 minutes for CDNs
    private_paths=["/user/", "/account/"],
    exclude_paths=["/admin/"],
    vary_by=["Accept", "Accept-Encoding"]
)

app.add_middleware(EdgeCacheMiddleware, config=cache_config)
```
#### RateLimitMiddleware
Protects your API from abuse by limiting the number of requests per client.
```python
from midstar.core.backend import RedisBackend
from midstar.middleware import RateLimitMiddleware

redis_client = Redis(host="localhost", port=6379)
storage_backend = RedisBackend(redis_client)

app.add_middleware(
    RateLimitMiddleware,
    storage_backend=storage_backend,
    requests_per_minute=100,
    window_size=60
)
```
#### ConcurrentRequestMiddleware
Limits the number of concurrent requests to prevent server overload.
```python
from midstar.middleware import ConcurrentRequestMiddleware

app.add_middleware(
    ConcurrentRequestMiddleware,
    max_concurrent_requests=100
)
```
#### HTTP2PushMiddleware
Enables HTTP/2 Server Push to proactively send critical resources to the client.

```python
from midstar.middleware import HTTP2PushMiddleware

app.add_middleware(
    HTTP2PushMiddleware,
    push_resources={
        "/": ["/static/css/main.css", "/static/js/app.js"],
        "/blog": ["/static/css/blog.css", "/static/images/header.png"]
    },
)
```
#### CompressionMiddleware
Automatically compresses HTTP responses to reduce bandwidth usage and improve load times.

```python
from midstar.middleware import CompressionMiddleware

app.add_middleware(
    CompressionMiddleware,
    minimum_size=1000,  # Only compress responses larger than 1KB
    compressible_content_types=["text/html", "text/css", "application/javascript", "application/json"],
    compression_level=6  # Compression level (1-9, where 9 is highest compression)
)
```
### Error Handling Middleware

#### ErrorHandlerMiddleware
Provides centralized error handling and customized error responses for your application.

```python
from midstar.middleware import ErrorHandlerMiddleware, ErrorConfig
from starlette.responses import JSONResponse

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
app.add_middleware(
    ErrorHandlerMiddleware,
    handlers={
        ValidationError: handle_validation_error,
    },
    log_exceptions=True
)
```

#### ValidationMiddleware
Automatically validates request data against predefined schemas.

```python
from midstar.middleware import ValidationMiddleware
from pydantic import BaseModel

class UserSchema(BaseModel):
    username: str
    email: str
    age: int

app.add_middleware(
    ValidationMiddleware,
    validators={
        "/users": {"POST": UserSchema},
        "/users/{user_id}": {"PUT": UserSchema}
    },
    response_class=JSONResponse
)
```

### Backend Storage Options
Midstar supports multiple backend storage options for rate limiting and other features:

RedisBackend
```python
from redis.asyncio import Redis
from midstar.core.backend import RedisBackend

redis_client = Redis(host="localhost", port=6379)
backend = RedisBackend(redis_client)
```
InMemoryBackend
```python
from midstar.core.backend import InMemoryBackend

backend = InMemoryBackend()
```


## License
This project is licensed under the MIT License - see the LICENSE file for details.