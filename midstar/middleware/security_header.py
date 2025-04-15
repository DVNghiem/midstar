from typing import Dict

from starlette.types import ASGIApp, Receive, Scope, Send


class SecurityHeadersConfig:
    def __init__(self, headers: Dict[str, str] = None):
        self.headers = headers or {
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        }


class SecurityHeadersMiddleware:
    """
    Security Headers Middleware for ASGI applications.

    This middleware adds security headers to HTTP responses based on a provided configuration.
    It intercepts HTTP responses, adds the configured security headers, and passes the
    enhanced response to the client.

    Attributes:
        app (ASGIApp): The ASGI application.
        config (SecurityHeadersConfig): Configuration object containing security headers.

    Example:
        ```python

        config = SecurityHeadersConfig(
            headers={
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'"
            }

        app = SecurityHeadersMiddleware(app, config)
        ```
    """

    def __init__(self, app: ASGIApp, config: SecurityHeadersConfig):
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False
        response_headers = []

        async def wrapped_send(event):
            nonlocal response_started, response_headers
            if event["type"] == "http.response.start":
                if response_started:
                    return
                response_started = True
                response_headers = event.get("headers", [])[:]
                response_headers.extend(
                    [[k.encode(), v.encode()] for k, v in self.config.headers.items()]
                )
                await send(
                    {
                        "type": "http.response.start",
                        "status": event["status"],
                        "headers": response_headers,
                    }
                )
            elif event["type"] == "http.response.body":
                await send(event)

        await self.app(scope, receive, wrapped_send)
