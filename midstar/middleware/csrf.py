import hashlib
import hmac
import json
import secrets
import time
from base64 import b64decode, b64encode
from typing import Dict

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class CSRFConfig:
    def __init__(self, token_lifetime: int = 3600, secret_key: bytes = None):
        self.token_lifetime = token_lifetime
        self.secret_key = secret_key or secrets.token_bytes(32)


class CSRFProtectionMiddleware:
    """CSRF Protection Middleware for ASGI applications.

    This middleware provides Cross-Site Request Forgery (CSRF) protection for ASGI web applications.
    It validates CSRF tokens for unsafe HTTP methods (POST, PUT, DELETE, PATCH) and rejects
    requests with invalid or missing tokens.

    The middleware works by generating secure tokens that combine session information with
    a timestamp, which are signed using HMAC-SHA256 and then validated on subsequent requests.

    Usage:
        app = CSRFProtectionMiddleware(app, config=CSRFConfig(
            secret_key=b"your-secret-key",
            token_lifetime=3600  # 1 hour
        ))

    Workflow:
    1. Generate a CSRF token using the `generate_csrf_token()` method
    2. Include this token in forms or as a header in AJAX requests
    3. The middleware will automatically validate the token on unsafe HTTP methods

    The middleware rejects requests with a 401 Unauthorized status when CSRF validation fails.

    Attributes:
        app (ASGIApp): The ASGI application being wrapped
        config (CSRFConfig): Configuration object containing settings like secret_key and token_lifetime
    """
    def __init__(self, app: ASGIApp, config: CSRFConfig):
        self.app = app
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            csrf_token = request.headers.get("X-CSRF-Token")
            if not csrf_token or not self._validate_csrf_token(csrf_token):
                await self._send_error_response(
                    401, {"message": "Invalid CSRF token"}, send
                )
                return

        await self.app(scope, receive, send)

    def generate_csrf_token(self, request: Request) -> str:
        """
        Generate a CSRF (Cross-Site Request Forgery) token for the given request.

        The token is created by combining the session ID (or client host if session ID is not available)
        with the current timestamp, signing it using HMAC-SHA256 with the configured secret key,
        and then base64 encoding the result.

        Args:
            request (Request): The request object for which to generate a CSRF token.
                This is expected to have a scope dictionary and client attribute.

        Returns:
            str: A base64-encoded string containing the session ID, timestamp,
                 and signature that can be used as a CSRF token.

        Note:
            This method also sets the 'session_id' in the request scope.
        """
        session_id = request.scope.get("session_id", request.client.host)
        timestamp = str(int(time.time()))
        token_data = f"{session_id}:{timestamp}"
        signature = hmac.new(
            self.config.secret_key, token_data.encode(), hashlib.sha256
        ).digest()
        token = b64encode(
            f"{token_data}:{b64encode(signature).decode()}".encode()
        ).decode()
        request.scope["session_id"] = session_id
        return token

    def _validate_csrf_token(self, token: str) -> bool:
        """
        Validate the CSRF token.

        This method verifies the CSRF token by decoding it, extracting its components,
        checking if the token has expired, and validating the signature.

        Args:
            token (str): The CSRF token to validate.

        Returns:
            bool: True if the token is valid, False otherwise.

        The token is considered valid if:
        1. It can be properly decoded and split into session_id, timestamp, and signature.
        2. It has not expired (based on the configured token_lifetime).
        3. Its signature matches the expected signature generated using the secret key.
        """
        try:
            decoded_token = b64decode(token.encode()).decode()
            session_id, timestamp, signature = decoded_token.rsplit(":", 2)
            token_time = int(timestamp)
            current_time = int(time.time())
            if current_time - token_time > self.config.token_lifetime:
                return False
            expected_data = f"{session_id}:{timestamp}"
            expected_signature = hmac.new(
                self.config.secret_key, expected_data.encode(), hashlib.sha256
            ).digest()
            actual_signature = b64decode(signature)
            return hmac.compare_digest(expected_signature, actual_signature)
        except (ValueError, AttributeError, TypeError):
            return False

    async def _send_error_response(
        self, status: int, content: Dict, send: Send
    ) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [[b"content-type", b"application/json"]],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(content).encode(),
            }
        )
