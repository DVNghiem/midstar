import gzip
import zlib
from typing import List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CompressionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for compressing response content using gzip or deflate encoding.
    """

    def __init__(
        self,
        min_size: int = 500,
        compression_level: int = 6,
        include_types: Optional[List[str]] = None,
        *args,
        **kwargs,
    ) -> None:
        """
        Initialize compression middleware.

        Args:
            min_size: Minimum response size in bytes to trigger compression
            compression_level: Compression level (1-9, higher = better compression but slower)
            include_types: List of content types to compress (defaults to common text types)
        """
        super().__init__(*args, **kwargs)
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

    def before_request(self, request: Request) -> Request:
        return request

    async def dispatch(self, request: Request, call_next) -> Response:
        # Call the next middleware or endpoint
        response: Response = await super().dispatch(request, call_next)

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
            or len(response.body.encode()) < self.min_size
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
