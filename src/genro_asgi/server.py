# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
ASGI Server - Root dispatcher for multi-app architecture.

Two modes: flat (mount by path) or router (genro_routes).
See specifications/01-overview.md for architecture documentation.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .dispatcher import Dispatcher
from .lifespan import ServerLifespan
from .middleware import middleware_chain
from .response import Response
from .request import RequestRegistry, BaseRequest
from .server_config import ServerConfig
from .types import Receive, Scope, Send

from genro_routes import RoutedClass, Router, route  # type: ignore[import-untyped]

__all__ = ["AsgiServer"]


class AsgiServer(RoutedClass):
    """
    Base ASGI server with routing via genro_routes.

    Attributes:
        apps: Dict for mounted apps.
        router: genro_routes Router for dispatch.
        config: ServerConfig for configuration.
        dispatcher: Dispatcher handling request routing.
        logger: Server logger instance.
        lifespan: ServerLifespan for startup/shutdown.
        request_registry: RequestRegistry for tracking requests.
        request: Current request (from ContextVar).
        response: Current response builder.
    """

    __slots__ = (
        "apps",
        "router",
        "config",
        "logger",
        "lifespan",
        "request_registry",
        "dispatcher",
        "__dict__",
    )

    def __init__(
        self,
        server_dir: str | None = None,
        host: str | None = None,
        port: int | None = None,
        reload: bool | None = None,
        argv: list[str] | None = None,
    ) -> None:
        """Initialize AsgiServer."""
        self.config = ServerConfig(server_dir, host, port, reload, argv)
        self.apps: dict[str, RoutedClass] = {}
        self.router = Router(self, name="root")
        for name, opts in self.config.get_plugin_specs().items():
            self.router.plug(name, **opts)
        self.logger = logging.getLogger("genro_asgi")
        self.lifespan = ServerLifespan(self)
        self.request_registry = RequestRegistry()
        self.dispatcher = middleware_chain(self.config.middleware, Dispatcher(self))
        for name, (cls, kwargs) in self.config.get_app_specs().items():
            instance = cls(self, **kwargs)
            self.apps[name] = instance
            self.router.attach_instance(instance, name=name)

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
            await self.dispatcher(scope, receive, send)

    def run(self) -> None:
        """Run the server using Uvicorn."""
        import uvicorn

        host = self.config.server.host
        port = self.config.server.port
        reload = self.config.server.reload or False

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

    @route("root", mime_type="text/html")
    def index(self) -> str:
        """Default index page for router mode."""
        html_path = Path(__file__).parent / "resources" / "html" / "default_index.html"
        return html_path.read_text()

    @property
    def request(self) -> BaseRequest | None:
        """Current request from registry."""
        return self.request_registry.current

    @property
    def response(self) -> Response | None:
        """Current response from request."""
        req = self.request
        return req.response if req else None


if __name__ == "__main__":
    server = AsgiServer()
    server.run()
