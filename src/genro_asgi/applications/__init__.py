# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Application classes for genro-asgi.

Exports:
    AsgiApplication: Base class for apps mounted on AsgiServer.
    StaticSite: App for serving static files.
"""

from .base import AsgiApplication
from .static_site import StaticSite

__all__ = ["AsgiApplication", "StaticSite"]
