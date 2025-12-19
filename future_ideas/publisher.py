# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""AsgiPublisher - Extended server with multi-app mounting and system routes."""

from __future__ import annotations

from genro_routes import RoutingClass

from .base import AsgiServer
from ..dispatcher import Dispatcher
from ..response import JSONResponse
from ..types import Receive, Scope, Send

__all__ = ["AsgiPublisher", "PublisherDispatcher"]


class PublisherDispatcher(Dispatcher):
    """Dispatcher with system routes support."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Dispatch with system routes handling."""
        path = scope.get("path", "/")

        # Handle system routes
        if path.startswith("/system/"):
            await self._handle_system(scope, receive, send, path)
            return

        await super().__call__(scope, receive, send)

    async def _handle_system(
        self, scope: Scope, receive: Receive, send: Send, path: str
    ) -> None:
        """Handle /system/* routes."""
        endpoint = path[8:]  # strip "/system/"

        if endpoint == "health":
            response = JSONResponse({"status": "healthy"})
        elif endpoint == "apps":
            # List mounted apps - need access to server
            response = JSONResponse({"apps": list(self._get_apps().keys())})
        else:
            response = JSONResponse({"error": f"Unknown system endpoint: {endpoint}"}, status_code=404)

        await response(scope, receive, send)

    def _get_apps(self) -> dict[str, RoutingClass]:
        """Get apps dict from server."""
        return self.server.apps


class AsgiPublisher(AsgiServer):
    """
    Extended ASGI server with multi-app mounting and system routes.

    Adds:
        - mount() for mounting RoutingClass apps at paths
        - /system/* endpoints (health, apps, etc.)
        - PublisherDispatcher for extended routing

    Example:
        >>> publisher = AsgiPublisher()
        >>> publisher.mount("/shop", ShopApp())
        >>> publisher.mount("/accounting", AccountingApp())
        >>> publisher.run()
    """

    def _configure_server(self) -> None:
        """Replace dispatcher with PublisherDispatcher."""
        self.dispatcher = PublisherDispatcher(self)

    def mount(self, path: str, app: RoutingClass) -> None:
        """
        Mount a RoutingClass application at a path.

        Args:
            path: Mount path (e.g., "/api", "/shop"). Must be unique.
            app: RoutingClass instance to mount.

        Raises:
            ValueError: If path is already mounted.
        """
        # Normalize path
        if not path.startswith("/"):
            path = "/" + path
        if path.endswith("/") and path != "/":
            path = path.rstrip("/")

        if path in self.apps:
            raise ValueError(f"Path {path!r} is already mounted")

        self.apps[path] = app

        name = path.strip("/").replace("/", "_") or "root"
        self.router.attach_instance(app, name=name)

    def __repr__(self) -> str:
        """Return string representation."""
        apps_str = ", ".join(f"{path!r}" for path in self.apps)
        return f"AsgiPublisher(apps=[{apps_str}])"


if __name__ == "__main__":
    publisher = AsgiPublisher()
    publisher.run()
