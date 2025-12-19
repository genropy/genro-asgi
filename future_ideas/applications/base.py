# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""AsgiApplication - Base class for ASGI applications.

Apps mounted on AsgiServer should inherit from this class.
Provides routing via RoutingClass and access to server context.

Usage:
    from genro_asgi import AsgiApplication

    class MyApp(AsgiApplication):
        @route("index")
        def index(self):
            return Response("Hello")
"""

from __future__ import annotations

from genro_routes import RoutingClass  # type: ignore[import-untyped]

__all__ = ["AsgiApplication"]


class AsgiApplication(RoutingClass):
    """Base class for apps mounted on AsgiServer.

    Inherits routing from RoutingClass. Apps can define routes
    using @route decorator and will be attached to server's router.
    """
    pass


if __name__ == "__main__":
    pass
