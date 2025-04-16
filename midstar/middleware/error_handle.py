import asyncio
import html
import json
import logging
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from starlette.types import ASGIApp, Receive, Scope, Send

from midstar.core.types import STATUS_PHRASES, ErrorMode, ErrorResponseFormat

logger = logging.getLogger("asgi.error")


class ErrorHandlingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        debug: bool = False,
        mode: ErrorMode = ErrorMode.PRODUCTION,
        default_format: ErrorResponseFormat = ErrorResponseFormat.AUTO,
        handlers: Optional[Dict[Type[Exception], Callable]] = None,
        log_exceptions: bool = False,
        hide_error_details: Optional[List[Type[Exception]]] = None,
        custom_error_templates: Optional[Dict[int, str]] = None,
        default_headers: Optional[List[Tuple[bytes, bytes]]] = None,
        default_status_code: int = 500,
        include_cors_headers: bool = True,
        cors_allow_origin: str = "*",
    ):
        """
        Initialize the error handling middleware.

        Parameters
        ----------
        app : ASGIApp
            The ASGI application.
        debug : bool, default=False
            Enable debug mode, which overrides the mode parameter to ErrorMode.DEBUG.
        mode : ErrorMode, default=ErrorMode.PRODUCTION
            The error handling mode (ignored if debug=True).
        default_format : ErrorResponseFormat, default=ErrorResponseFormat.AUTO
            The default format for error responses.
        handlers : Dict[Type[Exception], Callable], optional
            Custom exception handlers mapping exception types to handler functions.
        log_exceptions : bool, default=False
            Whether to log exceptions when they occur.
        hide_error_details : List[Type[Exception]], optional
            Exception types for which detailed error information should be hidden.
        custom_error_templates : Dict[int, str], optional
            Custom error templates for specific HTTP status codes.
        default_headers : List[Tuple[bytes, bytes]], optional
            Default headers to include in error responses.
        default_status_code : int, default=500
            Default HTTP status code for unhandled exceptions.
        include_cors_headers : bool, default=True
            Whether to include CORS headers in error responses.
        cors_allow_origin : str, default="*"
            Value for the Access-Control-Allow-Origin header when CORS is enabled.
        """
        self.app = app
        self.mode = mode if not debug else ErrorMode.DEBUG
        self.default_format = default_format
        self.handlers = handlers or {}
        self.log_exceptions = log_exceptions
        self.hide_error_details = hide_error_details or []
        self.custom_error_templates = custom_error_templates or {}
        self.default_headers = default_headers or []
        self.default_status_code = default_status_code
        self.include_cors_headers = include_cors_headers
        self.cors_allow_origin = cors_allow_origin

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def wrapped_send(message: Dict[str, Any]) -> None:
            try:
                await send(message)
            except Exception as exc:
                await self._handle_exception(exc, scope, receive, send)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception as exc:
            await self._handle_exception(exc, scope, receive, send)

    async def _handle_exception(
        self,
        exc: Exception,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        Handles exceptions that occur during request processing.

        This method is responsible for processing exceptions and generating appropriate HTTP
        responses based on the exception type and configured handlers. It supports custom
        exception handlers, different response formats (JSON, HTML, etc.), and debug/production
        error modes.

        Args:
            exc: The caught exception to handle.
            scope: ASGI connection scope dictionary containing request information.
            receive: ASGI receive channel for receiving messages from the client.
            send: ASGI send channel for sending messages to the client.

        Returns:
            None: This method handles sending the error response directly via the ASGI send channel.

        Flow:
            1. Logs the exception if logging is enabled
            2. Determines the appropriate HTTP status code
            3. Identifies the response format based on request headers
            4. Tries to find a matching custom handler for the exception type
                - If handler returns a complete response dict, sends it immediately
                - Otherwise, captures any custom data returned by the handler
            5. Creates a standardized error response structure
            6. Conditionally includes detailed debug information based on mode
            7. Incorporates any custom data from handlers
            8. Formats and sends the final error response with appropriate headers
        """
        if self.log_exceptions:
            logger.exception(f"Exception occurred while processing request: {str(exc)}")

        status_code = self._get_status_code(exc)

        response_format = self._determine_response_format(scope)

        for exc_type, handler in self.handlers.items():
            if isinstance(exc, exc_type):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        response = await handler(exc, scope)
                    else:
                        response = handler(exc, scope)

                    if (
                        isinstance(response, dict)
                        and "body" in response
                        and "headers" in response
                        and "status" in response
                    ):
                        await send(
                            {
                                "type": "http.response.start",
                                "status": response["status"],
                                "headers": response["headers"],
                            }
                        )
                        await send(
                            {
                                "type": "http.response.body",
                                "body": response["body"],
                            }
                        )
                        return

                    custom_data = response
                    break
                except Exception:
                    logger.exception("Exception in custom error handler")
                    custom_data = None
                    break
        else:
            custom_data = None

        error_message = str(exc)

        show_details = self.mode == ErrorMode.DEBUG
        if any(isinstance(exc, exc_type) for exc_type in self.hide_error_details):
            show_details = False

        error_data = {
            "error": {
                "status": status_code,
                "title": STATUS_PHRASES.get(status_code, "Error"),
                "message": error_message,
            }
        }

        if show_details:
            error_data["error"]["detail"] = {
                "exception": exc.__class__.__name__,
                "traceback": traceback.format_exception(*sys.exc_info()),
            }

        if custom_data:
            if isinstance(custom_data, dict):
                error_data.update(custom_data)
            else:
                error_data["error"]["custom_data"] = custom_data

        body, headers = self._format_error_response(
            error_data, response_format, status_code
        )

        if self.include_cors_headers:
            headers.append(
                (b"access-control-allow-origin", self.cors_allow_origin.encode())
            )
            headers.append((b"access-control-allow-credentials", b"true"))

        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )

    def _get_status_code(self, exc: Exception) -> int:
        """
        Extract HTTP status code from an exception.

        This method tries to determine an appropriate HTTP status code from an exception object
        by following these steps:
        1. Look for attributes named 'status_code', 'code', or 'status'
        2. Check if the exception class name contains 'HTTP' or 'Status' followed by a number
        3. Return the default status code if no valid code can be determined

        Args:
            exc (Exception): The exception to extract status code from

        Returns:
            int: An HTTP status code (between 100-599) or the default status code

        Examples:
            >>> _get_status_code(HTTPError(status_code=404))
            404
            >>> _get_status_code(HTTP404NotFound())
            404
        """
        for attr in ["status_code", "code", "status"]:
            if hasattr(exc, attr):
                try:
                    code = int(getattr(exc, attr))
                    if 100 <= code <= 599:
                        return code
                except (ValueError, TypeError):
                    pass

        exc_name = exc.__class__.__name__
        for code_str in ["HTTP", "Status"]:
            if code_str in exc_name:
                try:
                    code_part = exc_name.split(code_str)[1][:3]
                    code = int(code_part)
                    if 100 <= code <= 599:
                        return code
                except (IndexError, ValueError):
                    pass

        return self.default_status_code

    def _determine_response_format(self, scope: Dict[str, Any]) -> ErrorResponseFormat:
        """
        Determine the response format based on the request's Accept header.

        Args:
            scope (Dict[str, Any]): The ASGI connection scope which contains request information.

        Returns:
            ErrorResponseFormat: The determined response format.
            - Returns default_format if it's not AUTO.
            - Returns HTML if Accept header contains 'text/html'.
            - Returns JSON if Accept header contains 'application/json' or 'application/*'.
            - Returns TEXT otherwise.
        """
        if self.default_format != ErrorResponseFormat.AUTO:
            return self.default_format

        headers = scope.get("headers", [])
        accept = ""

        for name, value in headers:
            if name.lower() == b"accept":
                accept = value.decode("latin-1").lower()
                break

        if "text/html" in accept:
            return ErrorResponseFormat.HTML
        elif "application/json" in accept or "application/*" in accept:
            return ErrorResponseFormat.JSON
        else:
            return ErrorResponseFormat.TEXT

    def _format_error_response(
        self,
        error_data: Dict[str, Any],
        format_type: ErrorResponseFormat,
        status_code: int,
    ) -> Tuple[bytes, List[Tuple[bytes, bytes]]]:
        """
        Format the error response based on the requested format type.

        Supports three output formats:
        - JSON: Returns error data as a JSON object
        - HTML: Returns error data rendered in an HTML template (with traceback if available)
        - TEXT: Returns error data as plain text

        Parameters:
        -----------
        error_data : Dict[str, Any]
            Dictionary containing the error information, expected to have an 'error' key
            with title, message, and optional detail fields
        format_type : ErrorResponseFormat
            The desired format for the error response (JSON, HTML, or TEXT)
        status_code : int
            HTTP status code for the error

        Returns:
        --------
        Tuple[bytes, List[Tuple[bytes, bytes]]]
            A tuple containing:
            - The formatted error body as bytes
            - A list of HTTP headers as (name, value) tuples
        """

        headers = list(self.default_headers)

        if format_type == ErrorResponseFormat.JSON:
            body = json.dumps(error_data).encode("utf-8")
            headers.append((b"content-type", b"application/json; charset=utf-8"))

        elif format_type == ErrorResponseFormat.HTML:
            if status_code in self.custom_error_templates:
                template = self.custom_error_templates[status_code]
            else:
                template = self._get_default_html_template()

            error = error_data["error"]
            title = error["title"]
            message = html.escape(error["message"])
            details = ""

            if "detail" in error:
                if "traceback" in error["detail"]:
                    traceback_html = "<pre class='traceback'>"
                    for line in error["detail"]["traceback"]:
                        traceback_html += html.escape(line)
                    traceback_html += "</pre>"
                    details = f"<h3>Traceback</h3>{traceback_html}"

            body = template.format(
                title=title, status=status_code, message=message, details=details
            ).encode("utf-8")
            headers.append((b"content-type", b"text/html; charset=utf-8"))

        else:  # TEXT
            error = error_data["error"]
            body = f"Error {status_code}: {error['title']}\n\n{error['message']}"

            if "detail" in error and error["detail"].get("traceback"):
                body += "\n\nTraceback:\n"
                body += "".join(error["detail"]["traceback"])

            body = body.encode("utf-8")
            headers.append((b"content-type", b"text/plain; charset=utf-8"))

        return body, headers

    def _get_default_html_template(self) -> str:
        return """<!DOCTYPE html>
<html>
<head>
    <title>Error {status}: {title}</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, 
                         "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
        }}
        h1 {{
            color: #e53e3e;
            border-bottom: 1px solid #eee;
            padding-bottom: 0.5rem;
            margin-bottom: 1rem;
        }}
        .message {{
            background-color: #f8f9fa;
            border-left: 4px solid #e53e3e;
            padding: 1rem;
            margin-bottom: 1rem;
        }}
        .traceback {{
            background: #f8f9fa;
            padding: 1rem;
            overflow: auto;
            font-family: monospace;
            font-size: 0.9rem;
            line-height: 1.5;
        }}
        footer {{
            margin-top: 2rem;
            font-size: 0.8rem;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <h1>Error {status}: {title}</h1>
    <div class="message">{message}</div>
    {details}
    <footer>
        <p>If this problem persists, please contact the administrator.</p>
    </footer>
</body>
</html>
"""
