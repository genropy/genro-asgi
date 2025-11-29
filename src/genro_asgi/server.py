# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
ASGI Server - Root dispatcher for multi-app architecture.

Purpose
=======
AsgiServer is a root dispatcher that routes requests to specialized ASGI
applications based on the first path segment. Each app owns its path and
handles all sub-paths internally.

Features:
- Multi-app mount with flat path dispatch (first segment only)
- Lifespan management (startup/shutdown sequence)
- Auto-binding for apps that inherit AsgiServerEnabler
- 404 handling when no app matches

Architecture::

    ┌─────────────┐         ┌─────────────────────────────────────────────────────────┐
    │   Uvicorn   │         │  AsgiServer (Root Dispatcher)                           │
    │   :8000     │ ──────► │                                                         │
    │             │         │  Dispatch by first path segment:                        │
    │             │         │                                                         │
    │             │         │    /api/*     → apps["/api"]     (handles sub-paths)    │
    │             │         │    /stream/*  → apps["/stream"]  (handles sub-paths)    │
    │             │         │                                                         │
    └─────────────┘         └─────────────────────────────────────────────────────────┘

Definition::

    class AsgiServer:
        __slots__ = ("apps", "config", "logger", "lifespan", "_started")

        def __init__(self, config: dict | None = None)
        def mount(self, path: str, app: ASGIApp) -> None
        def run(self, host: str = None, port: int = None, **kwargs) -> None
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None

Example::

    from genro_asgi import AsgiServer, AsgiServerEnabler

    class BusinessApp(AsgiServerEnabler):
        async def __call__(self, scope, receive, send):
            # scope["path"] contains sub-path (e.g., "/users/123")
            self.binder.logger.info(f"Request: {scope['path']}")

    server = AsgiServer(config={"host": "0.0.0.0", "port": 8000})
    server.mount("/api", BusinessApp())      # handles /api, /api/users, /api/users/123
    server.mount("/stream", StreamingApp())  # handles /stream, /stream/events
    server.run()

Lifespan::

    Lifespan is managed by ServerLifespan class (self.lifespan):
    1. Startup: Sub-apps on_startup (registration order)
    2. Shutdown: Sub-apps on_shutdown (reverse order)

Design Notes
============
- Uses SmartOptions from genro-toolbox for config
- Path matching is exact on first segment (dict lookup O(1))
- Sub-apps receive remaining path and handle their own routing
- 404 for HTTP, close 4404 for WebSocket when no match
- Lifespan delegated to ServerLifespan for separation of concerns
"""

from __future__ import annotations

import logging
from typing import Any

from genro_toolbox import SmartOptions  # type: ignore[import-untyped]

from .binder import AsgiServerEnabler, ServerBinder
from .exceptions import HTTPException
from .lifespan import ServerLifespan
from .types import ASGIApp, Receive, Scope, Send

__all__ = ["AsgiServer"]


class AsgiServer:
    """
    Root ASGI dispatcher for multi-app architecture.

    Manages multiple ASGI applications mounted on different paths.
    Each app owns its path and handles all sub-paths internally.

    Attributes:
        apps: Dict mapping path to ASGI app.
        config: Server configuration as SmartOptions.
        logger: Server logger instance.
        lifespan: ServerLifespan instance managing startup/shutdown.

    Example:
        >>> server = AsgiServer(config={"debug": True})
        >>> server.mount("/api", api_app)
        >>> server.mount("/stream", stream_app)
        >>>
        >>> # Run with uvicorn
        >>> # uvicorn mymodule:server
    """

    __slots__ = ("apps", "config", "logger", "lifespan", "_started")

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize AsgiServer.

        Args:
            config: Optional configuration dict. Wrapped in SmartOptions.
        """
        self.apps: dict[str, ASGIApp] = {}
        self.config = SmartOptions(config or {})
        self.logger = logging.getLogger("genro_asgi")
        self.lifespan = ServerLifespan(self)
        self._started = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Handle ASGI request.

        Dispatches to mounted apps based on first path segment.
        Handles lifespan events via self.lifespan.

        Args:
            scope: ASGI scope dict.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        scope_type = scope["type"]

        # Handle lifespan via dedicated handler
        if scope_type == "lifespan":
            await self.lifespan(scope, receive, send)
            return

        # Dispatch HTTP/WebSocket
        app = self.get_app(scope)
        await app(scope, receive, send)

    def run(
        self,
        host: str | None = None,
        port: int | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Run the server using Uvicorn.

        Args:
            host: Host to bind (default: from config or "127.0.0.1").
            port: Port to bind (default: from config or 8000).
            **kwargs: Additional arguments passed to uvicorn.run().

        Example:
            >>> server = AsgiServer()
            >>> server.mount("/api", my_app)
            >>> server.run(host="0.0.0.0", port=8000)
        """
        import uvicorn

        # Get from args, config, or defaults
        run_host = host or self.config.get("host", "127.0.0.1")
        run_port = port or self.config.get("port", 8000)

        self.logger.info(f"Starting server on {run_host}:{run_port}")
        uvicorn.run(self, host=run_host, port=run_port, **kwargs)

    # ─────────────────────────────────────────────────────────────────────────
    # Helper methods
    # ─────────────────────────────────────────────────────────────────────────

    def mount(self, path: str, app: ASGIApp) -> None:
        """
        Mount an ASGI application at a path.

        The app will handle all requests starting with this path.
        Sub-paths are handled by the app itself.

        If app inherits from AsgiServerEnabler, a ServerBinder is
        automatically attached.

        Args:
            path: Mount path (e.g., "/api", "/stream"). Must be unique.
            app: ASGI application to mount.

        Raises:
            ValueError: If path is already mounted.

        Example:
            >>> server.mount("/api", api_app)      # handles /api/*
            >>> server.mount("/stream", stream_app)  # handles /stream/*
        """
        # Normalize path
        if not path.startswith("/"):
            path = "/" + path
        if path.endswith("/") and path != "/":
            path = path.rstrip("/")

        # Check for duplicate
        if path in self.apps:
            raise ValueError(f"Path {path!r} is already mounted")

        # Auto-bind if app supports it
        if isinstance(app, AsgiServerEnabler):
            app.binder = ServerBinder(self)

        self.apps[path] = app

    def get_app(self, scope: Scope) -> ASGIApp:
        """
        Get the app for a request and prepare scope with subpath.

        Extracts the first path segment to find the mounted app,
        then modifies scope in-place with root_path and remaining path.

        Args:
            scope: ASGI scope dict (modified in-place if app found).

        Returns:
            The matched app.

        Raises:
            HTTPException: 404 if no app matches the path.

        Example:
            >>> app = server.get_app(scope)
            >>> await app(scope, receive, send)
        """
        path = scope.get("path", "/")

        # Extract first segment: "/api/users/123" -> "/api"
        if path == "/":
            prefix = "/"
        else:
            parts = path.split("/", 2)  # ['', 'api', 'users/123'] or ['', 'api']
            prefix = "/" + parts[1] if len(parts) > 1 else "/"

        app = self.apps.get(prefix)
        if app is None:
            raise HTTPException(404, detail=f"Application not found: {prefix}")

        # Modify scope in-place for sub-app
        scope["root_path"] = scope.get("root_path", "") + prefix
        scope["path"] = path[len(prefix):] or "/"
        return app

    def __repr__(self) -> str:
        """Return string representation."""
        apps_str = ", ".join(f"{path!r}" for path in self.apps)
        return f"AsgiServer(apps=[{apps_str}])"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run AsgiServer")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    server = AsgiServer()
    server.run(host=args.host, port=args.port, reload=args.reload)
