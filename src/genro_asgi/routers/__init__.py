# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Router implementations for genro-asgi.

Exports:
    StaticRouter: Filesystem-backed router for serving static files.
"""

from .static_router import StaticRouter

__all__ = ["StaticRouter"]
