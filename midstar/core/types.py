from enum import Enum


class CompressionAlgorithm(str, Enum):
    GZIP = "gzip"
    DEFLATE = "deflate"
    BROTLI = "br"


class ErrorMode(str, Enum):
    DEBUG = "debug"
    PRODUCTION = "production"
    HYBRID = "hybrid"


class ErrorResponseFormat(str, Enum):
    JSON = "json"
    HTML = "html"
    TEXT = "text"
    AUTO = "auto"


STATUS_PHRASES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    409: "Conflict",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}
