# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ASGI Server - main entry point for genro-asgi applications.

AsgiServer is the central coordinator that:
- Loads configuration from YAML files (config.yaml)
- Mounts applications (AsgiApplication subclasses)
- Builds the middleware chain (auth, cors, errors)
- Handles ASGI lifespan protocol (startup/shutdown)
- Routes requests via genro-routes Router

Usage:
    from genro_asgi import AsgiServer

    server = AsgiServer(server_dir=".")
    server.run()  # Starts uvicorn

Configuration (config.yaml):
    server:
      host: "127.0.0.1"
      port: 8000
      reload: true

    middleware:
      cors: on
      auth: on

    apps:
      shop:
        module: "main:ShopApp"

    openapi:
      title: "My API"
      version: "1.0.0"

Architecture:
    AsgiServer(RoutingClass)
        ├── config: ServerConfig
        ├── router: Router (genro-routes)
        ├── dispatcher: Middleware chain → Dispatcher
        ├── lifespan: ServerLifespan
        ├── apps: dict[str, AsgiApplication]
        ├── storage: LocalStorage
        └── resource_loader: ResourceLoader

Request flow:
    ASGI Server (uvicorn) → AsgiServer.__call__
        → Middleware chain (errors → cors → auth)
        → Dispatcher → router.node(path, auth_tags)
        → handler(**query) → response.set_result()
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from .dispatcher import Dispatcher
from .exceptions import Redirect, HTTPNotFound
from .lifespan import ServerLifespan
from .middleware import middleware_chain
from .resources import ResourceLoader
from .response import Response
from .request import RequestRegistry, BaseRequest
from .server_config import ServerConfig
from .storage import LocalStorage
from .types import Receive, Scope, Send

from genro_routes import RoutingClass, Router, route  # type: ignore[import-untyped]

try:
    import jwt
    HAS_JWT = True
except ImportError:
    jwt = None  # type: ignore[assignment]
    HAS_JWT = False

__all__ = ["AsgiServer"]


class AsgiServer(RoutingClass):
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
        "base_dir",
        "logger",
        "lifespan",
        "request_registry",
        "dispatcher",
        "storage",
        "resource_loader",
        "openapi_info",
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
        self.base_dir: Path = self.config.server["server_dir"]
        self.apps: dict[str, RoutingClass] = {}
        self.router = Router(self, name="root")
        self.storage = LocalStorage(self.base_dir)
        self.resource_loader = ResourceLoader(self)
        for name, opts in self.config.get_plugin_specs().items():
            self.router.plug(name, **opts)
        self.logger = logging.getLogger("genro_asgi")
        self.lifespan = ServerLifespan(self)
        self.request_registry = RequestRegistry()
        self.dispatcher = middleware_chain(
            self.config.middleware, Dispatcher(self), full_config=self.config._opts
        )
        for name, (cls, kwargs) in self.config.get_app_specs().items():
            # Add app's base_dir to sys.path for imports
            base_dir = kwargs.get("base_dir")
            if base_dir and str(base_dir) not in sys.path:
                sys.path.insert(0, str(base_dir))
            instance = cls(**kwargs)
            instance._mount_name = name
            self.apps[name] = instance
            self.router.attach_instance(instance, name=name)

        # Set index as default_entry - it will redirect to main_app if configured
        self.router.default_entry = "index"

        # OpenAPI info from config (plain dict via property)
        self.openapi_info: dict[str, Any] = self.config.openapi

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
        import os
        import uvicorn

        host = self.config.server["host"]
        port = self.config.server["port"]
        reload = self.config.server["reload"] or False

        self.logger.info(f"Starting server on {host}:{port}")
        if reload:
            # Uvicorn requires import string for reload mode
            # Pass server_dir via env var for the factory
            os.environ["GENRO_ASGI_SERVER_DIR"] = str(self.base_dir)
            uvicorn.run(
                "genro_asgi:AsgiServer",
                host=host,
                port=port,
                reload=True,
                reload_dirs=[str(self.base_dir)],
                factory=True,
            )
        else:
            uvicorn.run(self, host=host, port=port)

    def __repr__(self) -> str:
        """Return string representation."""
        if self.router is not None:
            return f"AsgiServer(router={self.router.name!r})"
        apps_str = ", ".join(f"{path!r}" for path in self.apps)
        return f"AsgiServer(apps=[{apps_str}])"

    # ─────────────────────────────────────────────────────────────────────────
    # Router mode methods
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def main_app(self) -> str | None:
        """Return main app name: configured or single app."""
        configured: str | None = self.config["main_app"]
        if configured:
            return configured
        apps: dict[str, Any] = self.config["apps"]
        return next(iter(apps)) if len(apps) == 1 else None

    @route("root", meta_mime_type="text/html")
    def index(self) -> str:
        """Default index page for router mode. Redirects to main_app if configured or single."""
        if self.main_app:
            raise Redirect(f"/{self.main_app}/")
        html_path = Path(__file__).parent / "resources" / "html" / "default_index.html"
        return html_path.read_text()

    @route("root", meta_mime_type="application/json")
    def _openapi(self, *args: str) -> dict[str, Any]:
        """OpenAPI schema endpoint."""
        basepath = "/".join(args) if args else None
        paths = self.router.nodes(basepath=basepath, mode="openapi")
        return {
            "openapi": "3.1.0",
            "info": self.openapi_info,
            **paths,
        }

    @property
    def resources_path(self) -> Path | None:
        """Path to server's resources directory."""
        resources = self.base_dir / "resources"
        return resources if resources.is_dir() else None

    @route(name="_resource")
    def load_resource(self, *args: str, name: str) -> Any:
        """Load resource with hierarchical fallback.

        Callable directly by apps or via HTTP at /_resource?name=...

        Args:
            *args: Path segments in routing tree (e.g., "shop", "tables")
            name: Resource name to load

        Returns:
            Wrapped result with content and mime_type metadata

        Raises:
            HTTPNotFound: If resource not found
        """
        result = self.resource_loader.load(*args, name=name)
        if result is None:
            raise HTTPNotFound(f"Resource not found: {name}")

        content, mime_type = result
        return self.result_wrapper(content, mime_type=mime_type)

    @route("root", auth_tags="superadmin&has_jwt")
    def _create_jwt(
        self,
        jwt_config: str | None = None,
        sub: str | None = None,
        tags: str | None = None,
        exp: int | None = None,
        **extra_kwargs: Any,
    ) -> dict[str, Any]:
        """Create JWT token via HTTP endpoint. Requires superadmin auth tag."""
        if not jwt_config or not sub:
            return {"error": "jwt_config and sub are required"}
        # TODO: import create_jwt from genro-toolbox
        # tags_list = tags.split(",") if tags else None
        # extra = extra_kwargs if extra_kwargs else None
        # token = create_jwt(jwt_config, sub, tags_list, exp, extra)
        # return {"token": token}
        _ = (tags, exp, extra_kwargs)  # unused until genro-toolbox is ready
        return {"error": "not implemented - waiting for genro-toolbox"}

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
