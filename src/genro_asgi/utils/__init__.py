# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Utility classes for genro-asgi.

Exports:
    ServerBinder: Controlled interface to server resources.
    AsgiServerEnabler: Mixin for external apps that need server access.
"""

from .binder import AsgiServerEnabler, ServerBinder

__all__ = ["AsgiServerEnabler", "ServerBinder"]
