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
### Example Application
Here's a complete example setting up multiple middleware components:

```python
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from midstar.middleware import (
    RateLimitMiddleware,
    EdgeCacheMiddleware,
    ConcurrentRequestMiddleware,
    SecurityHeadersMiddleware,
    CacheConfig,
    SecurityHeadersConfig
)
from midstar.core.backend import InMemoryBackend

backend = InMemoryBackend()

app = Starlette(
    middleware=[
        Middleware(
            ConcurrentRequestMiddleware,
            max_concurrent_requests=100,
        ),
        Middleware(
            RateLimitMiddleware,
            storage_backend=backend,
            requests_per_minute=60,
            window_size=60
        ),
        Middleware(
            EdgeCacheMiddleware,
            config=CacheConfig(max_age=60)    
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

@app.route("/")
def hello(request):
    return PlainTextResponse("Hello, world!")
```

## License
This project is licensed under the MIT License - see the LICENSE file for details.