import gzip
import zlib
from typing import Awaitable, Callable, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from midstar.core.utils import get_streaming_response_body

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]
DispatchFunction = Callable[[Request, RequestResponseEndpoint], Awaitable[Response]]


class CompressionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for compressing response content using gzip or deflate encoding.
    """

    def __init__(
        self,
        app: ASGIApp,
        dispatch: DispatchFunction | None = None,
        min_size: int = 500,
        compression_level: int = 6,
        include_types: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize compression middleware.

        Args:
            min_size: Minimum response size in bytes to trigger compression
            compression_level: Compression level (1-9, higher = better compression but slower)
            include_types: List of content types to compress (defaults to common text types)
        """
        super().__init__(app, dispatch)
        self.min_size = min_size
        self.compression_level = compression_level
        self.include_types = include_types or [
            "text/plain",
            "text/html",
            "text/css",
            "text/javascript",
            "application/javascript",
            "application/json",
            "application/xml",
            "application/x-yaml",
        ]

    async def dispatch(self, request: Request, call_next) -> Response:
        # Call the next middleware or endpoint
        response: Response = await call_next(request)
        response_body = get_streaming_response_body(response)

        # Check if response should be compressed
        content_type = (
            (response.headers.get("content-type") or "").split(";")[0].lower()
        )
        content_encoding = (response.headers.get("content-encoding") or "").lower()

        # Skip if:
        # - Content is already encoded
        # - Content type is not in include list
        # - Content length is below minimum size
        if (
            content_encoding
            or content_type not in self.include_types
            or len(response_body) < self.min_size
        ):
            return response

        # Get accepted encodings from request
        accept_encoding = (response.headers.get("accept-encoding") or "").lower()

        if "gzip" in accept_encoding:
            # Use gzip compression
            response.body = gzip.compress(
                response.body
                if isinstance(response.body, bytes)
                else str(response.body).encode(),
                compresslevel=self.compression_level,
            )
            response.headers.set("content-encoding", "gzip")

        elif "deflate" in accept_encoding:
            # Use deflate compression
            response.body = zlib.compress(
                response.body
                if isinstance(response.body, bytes)
                else str(response.body).encode(),
                level=self.compression_level,
            )
            response.headers.set("content-encoding", "deflate")

        # Update content length after compression
        response.headers.set("content-length", str(len(response.body)))

        # Add Vary header to indicate content varies by Accept-Encoding
        response.headers.set("vary", "Accept-Encoding")

        return response
