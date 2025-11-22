"""ASGI Middleware collection.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

from .cors import CORSMiddleware
from .errors import ErrorMiddleware
from .compression import CompressionMiddleware
from .static import StaticFilesMiddleware

__all__ = [
    "CORSMiddleware",
    "ErrorMiddleware",
    "CompressionMiddleware",
    "StaticFilesMiddleware",
]
