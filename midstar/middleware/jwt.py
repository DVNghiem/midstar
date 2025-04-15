import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

class JWTMiddleware:
    """
    JWT Middleware for ASGI applications.

    This middleware handles JWT authentication for ASGI applications. It validates
    the JWT token in the Authorization header and adds the decoded payload to the
    request scope under the 'user' key.

    Attributes:
        app (ASGIApp): The ASGI application.
        jwt_secret (str): Secret key for JWT encoding/decoding.
        jwt_algorithm (str): Algorithm used for JWT encoding/decoding, default is "HS256".
        jwt_expires_in (int): Token expiration time in seconds, default is 3600 (1 hour).

    Usage:
        ```
        app = FastAPI()
        app.add_middleware(
            JWTMiddleware,
            jwt_secret="your-secret-key",
            jwt_algorithm="HS256",
            jwt_expires_in=3600
        ```

    Note:
        The middleware expects the JWT token to be included in the Authorization
        header using the Bearer scheme: "Authorization: Bearer <token>"
    """
    def __init__(
        self,
        app: ASGIApp,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        jwt_expires_in: int = 3600,
    ):
        self.app = app
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expires_in = jwt_expires_in

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            await self._send_error_response(
                401, {"message": "Authorization header missing or invalid"}, send
            )
            return

        token = auth_header.split(" ")[1]
        try:
            payload = self._verify_jwt_token(token)
            scope["user"] = payload
        except Exception as e:
            await self._send_error_response(401, {"message": str(e)}, send)
            return

        await self.app(scope, receive, send)

    async def _send_error_response(
        self, status: int, content: Dict, send: Send
    ) -> None:
        headers = [[b"content-type", b"application/json"]]
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(content).encode(),
            }
        )

    def _verify_jwt_token(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise Exception("Token has expired")
        except jwt.InvalidTokenError:
            raise Exception("Invalid token")

    def generate_jwt_token(self, user_data: Dict[str, Any]) -> str:
        if not self.jwt_secret:
            raise ValueError("JWT secret key is not configured")
        payload = {
            "user": user_data,
            "exp": datetime.now(tz=timezone.utc)
            + timedelta(seconds=self.jwt_expires_in),
            "iat": datetime.now(tz=timezone.utc),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
