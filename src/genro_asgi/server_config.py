# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Server configuration - handles all config loading and app instantiation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from genro_toolbox import SmartOptions  # type: ignore[import-untyped]

__all__ = ["ServerConfig"]

DEFAULTS = {"host": "127.0.0.1", "port": 8000, "reload": False}


def _server_opts_spec(
    server_dir: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Reference function for SmartOptions type extraction."""


class ServerConfig:
    """Handles server configuration loading and app instantiation."""

    __slots__ = ("_opts",)

    def __init__(
        self,
        server_dir: str | None = None,
        host: str | None = None,
        port: int | None = None,
        reload: bool | None = None,
        argv: list[str] | None = None,
    ) -> None:
        self._opts = self._build_config(
            server_dir=server_dir,
            host=host,
            port=port,
            reload=reload,
            argv=argv or [],
        )

    def _build_config(
        self,
        server_dir: str | None,
        host: str | None,
        port: int | None,
        reload: bool | None,
        argv: list[str],
    ) -> SmartOptions:
        """Build server configuration from multiple sources.

        Config precedence (later overrides earlier):
        1. Built-in DEFAULTS
        2. Global config: ~/.genro-asgi/config.yaml
        3. Project config: <server_dir>/config.yaml
        4. Environment variables: GENRO_ASGI_*
        5. Command line arguments
        6. Explicit constructor parameters
        """
        env_argv_opts = SmartOptions(_server_opts_spec, env="GENRO_ASGI", argv=argv)

        caller_opts = SmartOptions(
            dict(server_dir=server_dir, host=host, port=port, reload=reload),
            ignore_none=True,
        )

        resolved_server_dir = Path(caller_opts["server_dir"] or env_argv_opts["server_dir"] or ".").resolve()

        if str(resolved_server_dir) not in sys.path:
            sys.path.insert(0, str(resolved_server_dir))

        global_config_path = Path.home() / ".genro-asgi" / "config.yaml"
        if global_config_path.exists():
            global_config = SmartOptions(str(global_config_path))
        else:
            global_config = SmartOptions({})

        project_config = SmartOptions(str(resolved_server_dir / "config.yaml"))

        config = global_config + project_config

        server_opts = (
            SmartOptions(DEFAULTS)
            + (global_config["server"] or SmartOptions({}))
            + (project_config["server"] or SmartOptions({}))
            + env_argv_opts
            + caller_opts
        )
        server_opts["server_dir"] = resolved_server_dir

        config["server"] = server_opts
        return config

    @property
    def server(self) -> SmartOptions:
        """Server options (host, port, reload, server_dir)."""
        result: SmartOptions = self._opts["server"]
        return result

    @property
    def middleware(self) -> list[Any]:
        """Middleware configuration list."""
        return self._opts["middleware"] or []

    @property
    def plugins(self) -> SmartOptions | None:
        """Plugins configuration."""
        result: SmartOptions | None = self._opts["plugins"]
        return result

    @property
    def apps(self) -> SmartOptions | None:
        """Apps configuration."""
        result: SmartOptions | None = self._opts["apps"]
        return result

    def get_plugin_specs(self) -> dict[str, dict[str, Any]]:
        """Return {plugin_name: opts_dict} for all configured plugins."""
        if not self.plugins:
            return {}
        result = {}
        for plugin_name in self.plugins.as_dict():
            plugin_opts = self.plugins[plugin_name]
            if hasattr(plugin_opts, "as_dict"):
                plugin_opts = plugin_opts.as_dict()
            result[plugin_name] = plugin_opts or {}
        return result

    def get_app_specs(self) -> dict[str, tuple[type, dict[str, Any]]]:
        """Return {name: (cls, kwargs)} for all configured apps."""
        if not self.apps:
            return {}
        result: dict[str, tuple[type, dict[str, Any]]] = {}
        for name, app_opts in self.apps.as_dict().items():
            module_path, kwargs = self._parse_app_opts(name, app_opts)
            module_name, class_name = module_path.split(":")
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            result[name] = (cls, kwargs)
        return result

    def _parse_app_opts(self, name: str, app_opts: SmartOptions | dict | str) -> tuple[str, dict[str, Any]]:
        """Parse app options into module_path and kwargs."""
        if isinstance(app_opts, str):
            return app_opts, {}
        if isinstance(app_opts, dict):
            module_path = app_opts.get("module", "")
            if not module_path:
                raise ValueError(f"App '{name}' missing 'module' in config")
            kwargs = {k: v for k, v in app_opts.items() if k != "module"}
            return module_path, kwargs
        # SmartOptions
        module_path = app_opts["module"]
        if not module_path:
            raise ValueError(f"App '{name}' missing 'module' in config")
        kwargs = {k: v for k, v in app_opts.as_dict().items() if k != "module"}
        return module_path, kwargs

    def __getitem__(self, name: str) -> Any:
        """Proxy bracket access to underlying opts."""
        return self._opts[name]


if __name__ == "__main__":
    config = ServerConfig()
    print(f"Server: {config.server['host']}:{config.server['port']}")
    print(f"Middleware: {config.middleware}")
    print(f"Plugins: {config.plugins}")
