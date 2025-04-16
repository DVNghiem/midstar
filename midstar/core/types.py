from enum import Enum

class CompressionAlgorithm(str, Enum):
    GZIP = "gzip"
    DEFLATE = "deflate"
    BROTLI = "br"
