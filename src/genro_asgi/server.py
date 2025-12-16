# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
ASGI Server - Root dispatcher for multi-app architecture.

Two modes: flat (mount by path) or router (genro_routes).
See specifications/01-overview.md for architecture documentation.
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import Any

from genro_toolbox import SmartOptions  # type: ignore[import-untyped]

from .dispatcher import Dispatcher
from .lifespan import ServerLifespan
from .middleware import middleware_chain
from .response import Response
from .request import RequestRegistry
from .types import Receive, Scope, Send

from genro_routes import RoutedClass, Router, route  # type: ignore[import-untyped]

__all__ = ["AsgiServer"]

DEFAULTS = {"host": "127.0.0.1", "port": 8000, "reload": False}


def _server_opts_spec(
    app_dir: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Reference function for SmartOptions type extraction."""
    pass


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

    __slots__ = (
        "apps",
        "router",
        "opts",
        "logger",
        "lifespan",
        "request_registry",
        "dispatcher",
        "__dict__",
    )

    def __init__(
        self,
        app_dir: str | None = None,
        host: str | None = None,
        port: int | None = None,
        reload: bool | None = None,
        argv: list[str] | None = None,
    ) -> None:
        """Initialize AsgiServer. Config via _configure()."""
        self.opts = self._configure(
            app_dir=app_dir,
            host=host,
            port=port,
            reload=reload,
            argv=argv or [],
        )
        self.apps: dict[str, RoutedClass] = {}
        self.router = Router(self, name="root")
        self._apply_plugins(self.router)
        self.logger = logging.getLogger("genro_asgi")
        self.lifespan = ServerLifespan(self)
        self.request_registry = RequestRegistry()
        middleware_config = self.opts.middleware or []
        self.dispatcher = middleware_chain(middleware_config, Dispatcher(self))
        self.on_init()

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
        """Run the server using Uvicorn. Config from self.opts.server."""
        import uvicorn

        host = self.opts.server.host
        port = self.opts.server.port
        reload = self.opts.server.reload or False

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
        from .response import HTMLResponse

        html_path = Path(__file__).parent / "resources" / "html" / "default_index.html"
        return HTMLResponse(content=html_path.read_text())

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _configure(
        self,
        app_dir: str | None,
        host: str | None,
        port: int | None,
        reload: bool | None,
        argv: list[str],
    ) -> SmartOptions:
        """Build server configuration from multiple sources.

        Config precedence (later overrides earlier):
        1. Built-in DEFAULTS
        2. Global config: ~/.genro-asgi/config.yaml
        3. Project config: <app_dir>/config.yaml
        4. Environment variables: GENRO_ASGI_*
        5. Command line arguments
        6. Explicit constructor parameters
        """
        # Parse env + argv using _server_opts_spec for type conversion
        env_argv_opts = SmartOptions(_server_opts_spec, env="GENRO_ASGI", argv=argv)

        # Caller opts (explicit parameters, ignore None values)
        caller_opts = SmartOptions(
            dict(app_dir=app_dir, host=host, port=port, reload=reload),
            ignore_none=True,
        )

        # Resolve app_dir: caller > argv > env > default "."
        resolved_app_dir = Path(caller_opts.app_dir or env_argv_opts.app_dir or ".").resolve()

        if str(resolved_app_dir) not in sys.path:
            sys.path.insert(0, str(resolved_app_dir))

        # Load global config from ~/.genro-asgi/config.yaml
        global_config_path = Path.home() / ".genro-asgi" / "config.yaml"
        if global_config_path.exists():
            global_config = SmartOptions(str(global_config_path))
        else:
            global_config = SmartOptions({})

        # Load project config from file
        project_config = SmartOptions(str(resolved_app_dir / "config.yaml"))

        # Merge configs: global < project (project overrides global)
        config = global_config + project_config

        # Merge server opts: DEFAULTS < global.server < project.server < env < argv < caller
        server_opts = (
            SmartOptions(DEFAULTS)
            + (global_config.server or SmartOptions({}))
            + (project_config.server or SmartOptions({}))
            + env_argv_opts
            + caller_opts
        )
        server_opts.app_dir = resolved_app_dir

        # Update config with merged server options
        config.server = server_opts
        return config

    def _apply_plugins(self, router: Router) -> None:
        """Apply plugins from config to router.

        Config format (config.yaml):
            plugins:
              openapi: {}        # plugin name: config dict
              custom:
                opt1: value1
        """
        plugins_config = self.opts.plugins
        if not plugins_config:
            return
        for plugin_name in plugins_config.as_dict():
            plugin_opts = plugins_config[plugin_name]
            if hasattr(plugin_opts, "as_dict"):
                plugin_opts = plugin_opts.as_dict()
            router.plug(plugin_name, **(plugin_opts or {}))

    def on_init(self) -> None:
        """Hook for subclasses after init completes. Default: attach apps from config."""
        self._attach_instances()

    def _attach_instances(self) -> None:
        """Attach app instances from config."""
        apps_config = self.opts.apps
        if not apps_config:
            return
        for name, app_opts in apps_config.as_dict().items():
            self.attach_instance(name, app_opts)

    def attach_instance(self, name: str, app_opts: SmartOptions | dict | str) -> None:
        """Attach a single app instance from config.

        Args:
            name: Mount name for the app.
            app_opts: App configuration - SmartOptions or dict with:
                      - module: "module:Class" (required)
                      - other keys passed as kwargs to constructor
        """
        if isinstance(app_opts, str):
            module_path = app_opts
            kwargs: dict[str, Any] = {}
        elif isinstance(app_opts, dict):
            module_path = app_opts.get("module", "")
            if not module_path:
                raise ValueError(f"App '{name}' missing 'module' in config")
            kwargs = {k: v for k, v in app_opts.items() if k != "module"}
        else:
            # SmartOptions: access via attribute
            module_path = app_opts.module
            if not module_path:
                raise ValueError(f"App '{name}' missing 'module' in config")
            kwargs = {k: v for k, v in app_opts.as_dict().items() if k != "module"}

        module_name, class_name = module_path.split(":")
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        # Pass app_dir so apps can resolve relative paths
        kwargs["app_dir"] = self.opts.server.app_dir
        kwargs["_server"] = self
        instance = cls(**kwargs)
        self.apps[name] = instance

        # Only attach to router if it's a RoutedClass
        if hasattr(instance, "_routers"):
            self.router.attach_instance(instance, name=name)


if __name__ == "__main__":
    server = AsgiServer()
    server.run()
