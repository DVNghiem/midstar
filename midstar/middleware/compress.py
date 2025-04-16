import gzip
import io
import zlib
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from starlette.types import ASGIApp

try:
    import brotli
    BROTLI_SUPPORTED = True
except ImportError:
    BROTLI_SUPPORTED = False

from midstar.core.types import CompressionAlgorithm


class CompressionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        compression_level: int = 6,
        allowed_algorithms: Optional[Set[CompressionAlgorithm]] = None,
        exclude_paths: Optional[List[str]] = None,
        exclude_extensions: Optional[List[str]] = None,
        compressible_content_types: Optional[List[str]] = None,
    ):
        """
        Initialize the compression middleware.
        This middleware compresses HTTP responses based on client capabilities
        and configuration settings.
        Parameters
        ----------
        app : ASGIApp
            The ASGI application to wrap.
        minimum_size : int, default=500
            Minimum response size in bytes required for compression.
        compression_level : int, default=6
            Compression level (1-9, where 9 is highest compression).
        allowed_algorithms : Set[CompressionAlgorithm], optional
            Set of allowed compression algorithms. Defaults to GZIP and DEFLATE,
            with BROTLI if supported.
        exclude_paths : List[str], optional
            List of URL paths to exclude from compression.
        exclude_extensions : List[str], optional
            List of file extensions to exclude from compression.
        compressible_content_types : List[str], optional
            List of content types that should be compressed. Partial matches are
            supported (e.g., "text/" will match all text types).
        """
        self.app = app
        self.minimum_size = minimum_size
        self.compression_level = compression_level
        self.exclude_paths = exclude_paths or []
        self.exclude_extensions = exclude_extensions or []

        # default allowed algorithms
        if allowed_algorithms is None:
            allowed_algorithms = {
                CompressionAlgorithm.GZIP,
                CompressionAlgorithm.DEFLATE,
            }
            if BROTLI_SUPPORTED:
                allowed_algorithms.add(CompressionAlgorithm.BROTLI)
        self.allowed_algorithms = allowed_algorithms

        # Default compressible content types
        self.compressible_content_types = compressible_content_types or [
            "text/",
            "application/javascript",
            "application/json",
            "application/xml",
            "application/xhtml+xml",
            "image/svg+xml",
            "application/wasm",
            "application/font-woff",
            "application/font-woff2",
            "application/vnd.ms-fontobject",
            "application/x-font-ttf",
            "font/",
        ]

    async def __call__(
        self,
        scope: Dict[str, Any],
        receive: Callable[[], Awaitable[Dict[str, Any]]],
        send: Callable[[Dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # check if the request is a excluded path
        path = scope.get("path", "")
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                await self.app(scope, receive, send)
                return

        # check if the request file is a excluded extension
        for exclude_ext in self.exclude_extensions:
            if path.endswith(exclude_ext):
                await self.app(scope, receive, send)
                return

        # determine the compression algorithm based on the request headers
        accepted_encodings = self._get_accepted_encodings(scope)
        algorithm = self._select_compression_algorithm(accepted_encodings)

        if algorithm is None:
            await self.app(scope, receive, send)
            return

        response_body = io.BytesIO()
        response_headers = []
        response_started = False
        response_status = 200
        content_type = ""
        should_compress = False

        async def wrapped_send(message: Dict[str, Any]) -> None:
            nonlocal \
                response_started, \
                response_headers, \
                response_status, \
                content_type, \
                should_compress

            if message["type"] == "http.response.start":
                response_started = True
                response_status = message["status"]
                headers = message.get("headers", [])

                content_type = ""
                for name, value in headers:
                    if name.lower() == b"content-type":
                        content_type = value.decode("latin-1")
                        break

                # check content type is compressible
                should_compress = self._is_compressible_content_type(content_type)

                # check header is containing content-encoding
                has_content_encoding = any(
                    name.lower() == b"content-encoding" for name, _ in headers
                )

                # check if the response is compressible and not already compressed
                if (
                    has_content_encoding
                    or not should_compress
                    or response_status < 200
                    or response_status >= 300
                ):
                    await send(message)
                    should_compress = False
                else:
                    response_headers = headers
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                more_body = message.get("more_body", False)

                if not should_compress:
                    await send(message)
                    return

                response_body.write(body)

                if not more_body:
                    # if the response is complete, compress the content
                    content = response_body.getvalue()

                    # only compress if the content is large enough
                    if len(content) >= self.minimum_size:
                        compressed_content = self._compress_content(content, algorithm)

                        new_headers = []
                        for name, value in response_headers:
                            # skip content-length header beause it will be replaced
                            if name.lower() != b"content-length":
                                new_headers.append((name, value))

                        new_headers.append(
                            (b"content-encoding", algorithm.value.encode("latin-1"))
                        )
                        # Add vary header to indicate that the response can vary based on encoding
                        new_headers.append((b"vary", b"accept-encoding"))
                        new_headers.append(
                            (
                                b"content-length",
                                str(len(compressed_content)).encode("latin-1"),
                            )
                        )

                        await send(
                            {
                                "type": "http.response.start",
                                "status": response_status,
                                "headers": new_headers,
                            }
                        )
                        await send(
                            {
                                "type": "http.response.body",
                                "body": compressed_content,
                                "more_body": False,
                            }
                        )
                    else:
                        await send(
                            {
                                "type": "http.response.start",
                                "status": response_status,
                                "headers": response_headers,
                            }
                        )
                        await send(
                            {
                                "type": "http.response.body",
                                "body": content,
                                "more_body": False,
                            }
                        )
            else:
                await send(message)

        await self.app(scope, receive, wrapped_send)

    def _get_accepted_encodings(self, scope: Dict[str, Any]) -> List[str]:
        """
        Extract and parse the 'Accept-Encoding' header from the request scope.

        Searches for the 'Accept-Encoding' header in the request headers and parses
        its value into a list of supported encodings.

        Args:
            scope: Dict[str, Any] - The ASGI connection scope containing the request headers.

        Returns:
            List[str] - A list of accepted encodings extracted from the header.
                       Returns an empty list if no 'Accept-Encoding' header is found.

        Example:
            If the 'Accept-Encoding' header is 'gzip, deflate, br', this method
            will return ['gzip', 'deflate', 'br'].
        """
        headers = scope.get("headers", [])
        accept_encoding = ""

        for name, value in headers:
            if name.lower() == b"accept-encoding":
                accept_encoding = value.decode("latin-1")
                break

        if not accept_encoding:
            return []

        return [encoding.strip() for encoding in accept_encoding.split(",")]

    def _select_compression_algorithm(
        self, accepted_encodings: List[str]
    ) -> Optional[CompressionAlgorithm]:
        """
        Selects the most appropriate compression algorithm based on client's accepted encodings.

        The algorithm selection prioritizes in the following order:
        1. Brotli (if supported and allowed)
        2. GZip (if allowed)
        3. Deflate (if allowed)

        Args:
            accepted_encodings (List[str]): List of encoding formats accepted by the client,
                                            typically from the HTTP Accept-Encoding header

        Returns:
            Optional[CompressionAlgorithm]: The selected compression algorithm, or None if
                                            no suitable algorithm is found or allowed
        """
        if (
            BROTLI_SUPPORTED
            and CompressionAlgorithm.BROTLI in self.allowed_algorithms
            and any(enc == "br" or enc.startswith("br;") for enc in accepted_encodings)
        ):
            return CompressionAlgorithm.BROTLI

        if CompressionAlgorithm.GZIP in self.allowed_algorithms and any(
            enc == "gzip" or enc.startswith("gzip;") for enc in accepted_encodings
        ):
            return CompressionAlgorithm.GZIP

        if CompressionAlgorithm.DEFLATE in self.allowed_algorithms and any(
            enc == "deflate" or enc.startswith("deflate;") for enc in accepted_encodings
        ):
            return CompressionAlgorithm.DEFLATE

        return None

    def _is_compressible_content_type(self, content_type: str) -> bool:
        """
        Determines whether a content type is compressible.

        This method checks if a given content type matches any of the compressible content types
        defined in the middleware configuration.

        Args:
            content_type (str): The Content-Type header value to check.

        Returns:
            bool: True if the content type is compressible, False otherwise.

        Notes:
            - The method splits the content type on semicolons and only considers the first part,
              ignoring parameters like charset.
            - The comparison is done case-insensitively.
            - The method returns False if content_type is falsy (None, empty string, etc.).
        """
        if not content_type:
            return False

        content_type = content_type.split(";")[0].strip().lower()

        for compressible_type in self.compressible_content_types:
            if content_type.startswith(compressible_type):
                return True

        return False

    def _compress_content(
        self, content: bytes, algorithm: CompressionAlgorithm
    ) -> bytes:
        """
        Compresses content using the specified algorithm.

        Parameters:
            content (bytes): The content to compress.
            algorithm (CompressionAlgorithm): The compression algorithm to use.
                Supported algorithms are GZIP, DEFLATE, and BROTLI (if supported).

        Returns:
            bytes: The compressed content or the original content if the algorithm
            is not supported.

        Note:
            The compression level is determined by the instance's compression_level attribute.
            BROTLI compression is only applied if the brotli module is available.
        """
        if algorithm == CompressionAlgorithm.GZIP:
            compressor = gzip.GzipFile(
                fileobj=io.BytesIO(), mode="wb", compresslevel=self.compression_level
            )
            compressor.write(content)
            compressor.close()
            return compressor.fileobj.getvalue()

        elif algorithm == CompressionAlgorithm.DEFLATE:
            return zlib.compress(content, level=self.compression_level)

        elif algorithm == CompressionAlgorithm.BROTLI and BROTLI_SUPPORTED:
            return brotli.compress(content, quality=self.compression_level)

        return content

