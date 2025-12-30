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
        ├── server_application: ServerApplication (system endpoints)
        ├── sys_apps: dict[str, RoutingClass] (system apps)
        ├── apps: dict[str, AsgiApplication] (user apps)
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
from pathlib import Path
from typing import Any

from .dispatcher import Dispatcher
from .lifespan import ServerLifespan
from .loader import AppLoader
from .middleware import middleware_chain
from .resources import ResourceLoader
from .response import Response
from .request import RequestRegistry, BaseRequest
from .applications.server_application import ServerApplication
from .server_config import ServerConfig
from .storage import LocalStorage
from .types import Receive, Scope, Send

from genro_routes import RoutingClass, Router  # type: ignore[import-untyped]

__all__ = ["AsgiServer"]


class AsgiServer(RoutingClass):
    """
    Base ASGI server with routing via genro_routes.

    Attributes:
        config: ServerConfig for configuration.
        router: genro_routes Router for dispatch.
        dispatcher: Dispatcher handling request routing.
        lifespan: ServerLifespan for startup/shutdown.
        server_application: ServerApplication with system endpoints.
        sys_apps: Dict for system apps (mounted at /_sys/).
        apps: Dict for user apps.
        logger: Server logger instance.
        request_registry: RequestRegistry for tracking requests.
        request: Current request (from ContextVar).
        response: Current response builder.
    """

    __slots__ = (
        "config",
        "base_dir",
        "router",
        "storage",
        "resource_loader",
        "logger",
        "lifespan",
        "request_registry",
        "dispatcher",
        "openapi_info",
        "app_loader",
        "server_application",
        "sys_apps",
        "apps",
    )

    def __init__(
        self,
        server_dir: str | Path | None = None,
        host: str | None = None,
        port: int | None = None,
        reload: bool | None = None,
        argv: list[str] | None = None,
    ) -> None:
        """Initialize AsgiServer."""
        self.config = ServerConfig(server_dir, host, port, reload, argv)
        self.base_dir: Path = self.config.server["server_dir"]
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
        # OpenAPI info from config (plain dict via property)
        self.openapi_info: dict[str, Any] = self.config.openapi

        # Server application - system endpoints (/_server/)
        self.server_application = ServerApplication(server=self)
        self.router.attach_instance(self.server_application, name="_server")

        # AppLoader for isolated module loading (avoids sys.path pollution)
        self.app_loader = AppLoader()  # default prefix: "genro_root"

        # System apps (/_sys/) and user apps - loaded with same logic
        self.sys_apps: dict[str, RoutingClass] = {}
        self.apps: dict[str, RoutingClass] = {}

        self._load_apps(self.config.get_sys_app_specs_raw(), self.sys_apps, "_sys")
        self._load_apps(self.config.get_app_specs_raw(), self.apps)

        # Default entry points to server_application.index
        self.router.default_entry = "_server/index"

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

    def _load_apps(
        self,
        specs: dict[str, tuple[str, str, dict[str, Any]]],
        target: dict[str, RoutingClass],
        mount_prefix: str | None = None,
    ) -> None:
        """Load apps from specs into target dict and mount on router.

        Supports two module formats:
        1. Local modules (relative to server_dir): "main:Shop", "myapp.core:MyApp"
        2. Installed packages (absolute): "genro_asgi.sys_applications.swagger:SwaggerApp"

        Args:
            specs: Dict of {name: (module_name, class_name, kwargs)} from config.
            target: Dict to store loaded app instances (apps or sys_apps).
            mount_prefix: Optional prefix for mounting (e.g. "_sys" → "/_sys/name").
        """
        import importlib

        server_dir_path = self.config.server_dir

        for name, (module_name, class_name, kwargs) in specs.items():
            module_path = module_name.replace(".", "/")
            module_as_file = server_dir_path / f"{module_path}.py"
            module_as_dir = server_dir_path / module_path

            if module_as_file.exists() or module_as_dir.exists():
                # Local module: use AppLoader
                app_dir = server_dir_path if module_as_file.exists() else module_as_dir
                self.app_loader.load_package(name, app_dir)
                app_module = self.app_loader.get_module(name, module_name)
                if app_module is None:
                    raise ImportError(f"Cannot load module '{module_name}' for app '{name}'")
                kwargs["base_dir"] = app_dir
            else:
                # Installed package: use importlib
                app_module = importlib.import_module(module_name)
                module_file = getattr(app_module, "__file__", None)
                if module_file:
                    kwargs["base_dir"] = Path(module_file).parent

            cls = getattr(app_module, class_name)
            instance = cls(**kwargs)
            instance._mount_name = name
            target[name] = instance

            # Mount with prefix if specified (sys_apps → /_sys/name)
            mount_name = f"{mount_prefix}/{name}" if mount_prefix else name
            self.router.attach_instance(instance, name=mount_name)

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
