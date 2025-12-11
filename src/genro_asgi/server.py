# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
ASGI Server - Root dispatcher for multi-app architecture.

Two modes: flat (mount by path) or router (genro_routes).
See docs/architecture/01-server.md for full documentation.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from genro_toolbox import SmartOptions  # type: ignore[import-untyped]

from .dispatcher import Dispatcher
from .lifespan import ServerLifespan
from .response import Response
from .request import RequestRegistry
from .types import Receive, Scope, Send

from genro_routes import RoutedClass, Router, route

__all__ = ["AsgiServer"]


class AsgiServer(RoutedClass):
    """
    Base ASGI server with routing via genro_routes.

    Provides core ASGI handling with dispatcher pattern.
    For multi-app mounting, use AsgiPublisher instead.

    Attributes:
        apps: Dict for mounted apps (used by subclasses).
        router: genro_routes Router for dispatch.
        dispatcher: Dispatcher handling request routing.
        opts: Server configuration as SmartOptions.
        logger: Server logger instance.
        lifespan: ServerLifespan for startup/shutdown.
        request_registry: RequestRegistry for tracking requests.

    Subclassing:
        Override _configure_server() to replace self.dispatcher.
    """

    __slots__ = ("apps", "router", "opts", "logger", "lifespan", "request_registry", "dispatcher", "_started", "__dict__")

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        reload: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize AsgiServer. Config via _configure()."""
        self.opts = self._configure(host=host, port=port, reload=reload, **kwargs)
        self.apps: dict[str, RoutedClass] = {}
        self.router = Router(self, name="root")
        self.logger = logging.getLogger("genro_asgi")
        self.lifespan = ServerLifespan(self)
        self.request_registry = RequestRegistry()
        self.dispatcher = Dispatcher(self)
        self._started = False
        self._configure_server()
        self._attach_instances()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Handle ASGI request.

        Dispatches via genro_routes Router.
        Handles lifespan events via self.lifespan.

        Args:
            scope: ASGI scope dict.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
        else:
            await self.dispatcher.dispatch(scope, receive, send)

    def run(self) -> None:
        """Run the server using Uvicorn. Config from self.opts."""
        import uvicorn

        host = self.opts.get("host")
        port = self.opts.get("port")
        reload = self.opts.get("reload", False)

        self.logger.info(f"Starting server on {host}:{port}")
        uvicorn.run(self, host=host, port=port, reload=reload)

    def __repr__(self) -> str:
        """Return string representation."""
        if self.router is not None:
            return f"AsgiServer(router={self.router.name!r})"
        apps_str = ", ".join(f"{path!r}" for path in self.apps)
        return f"AsgiServer(apps=[{apps_str}])"

    # ─────────────────────────────────────────────────────────────────────────
    # Router mode methods
    # ─────────────────────────────────────────────────────────────────────────

    @route("root")
    def index(self) -> Response:
        """Default index page for router mode."""
        from .default_pages import DEFAULT_INDEX_HTML
        from .response import HTMLResponse
        return HTMLResponse(content=DEFAULT_INDEX_HTML)

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _configure(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        reload: bool = False,
        **kwargs: Any,
    ) -> SmartOptions:
        """Build server configuration from init params."""
        return SmartOptions({
            "host": host,
            "port": port,
            "reload": reload,
            **kwargs,
        })

    def _configure_server(self) -> None:
        """Hook for subclasses to configure server after init."""
        pass

    def _attach_instances(self) -> None:
        """Attach app instances from config."""
        apps_config = self.opts.get("apps", {})
        for name, spec in apps_config.items():
            self.attach_instance(name, spec)

    def attach_instance(self, name: str, spec: str) -> None:
        """Attach a single app instance from spec (module:Class)."""
        module_name, class_name = spec.split(":")
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        instance = cls()
        self.apps[name] = instance
        self.router.attach_instance(instance, name=name)


if __name__ == "__main__":
    server = AsgiServer()
    server.run()
