# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Middleware package - ASGI middleware for genro-asgi."""

from __future__ import annotations

import functools
import importlib
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send

MIDDLEWARE_REGISTRY: dict[str, type["BaseMiddleware"]] = {}


def headers_dict(
    func: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Decorator that parses headers into scope["_headers"] dict if not present."""

    @functools.wraps(func)
    async def wrapper(
        self: "BaseMiddleware", scope: "Scope", receive: "Receive", send: "Send"
    ) -> None:
        if "_headers" not in scope:
            scope["_headers"] = {
                name.decode("latin-1").lower(): value.decode("latin-1")
                for name, value in scope.get("headers", [])
            }
        await func(self, scope, receive, send)

    return wrapper


class BaseMiddleware(ABC):
    """Base class for all middleware. Subclasses auto-register via __init_subclass__.

    Class attributes:
        middleware_name: Registry key (default: class name).
        middleware_order: Order in chain (lower = earlier). Ranges:
            100: Core (errors)
            200: Logging/Tracing
            300: Security (cors, csrf)
            400: Authentication (auth)
            500-800: Business logic (custom)
            900: Transformation (compression, caching)
        middleware_default: Default on/off state. Default: False.

    Use @headers_dict decorator on __call__ to access scope["_headers"].
    """

    middleware_name: str = ""
    middleware_order: int = 500
    middleware_default: bool = False

    __slots__ = ("app",)

    def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        """Initialize middleware with wrapped app.

        Args:
            app: The ASGI app to wrap (next in chain).
            **kwargs: Middleware-specific configuration from YAML.
        """
        self.app = app

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Use middleware_name if set, otherwise derive from class name
        name = cls.middleware_name or cls.__name__
        if name in MIDDLEWARE_REGISTRY:
            raise ValueError(f"Middleware name '{name}' already registered")
        cls.middleware_name = name
        MIDDLEWARE_REGISTRY[name] = cls

    @abstractmethod
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...


def _autodiscover() -> None:
    """Import all middleware modules in this package to trigger registration."""
    package_dir = Path(__file__).parent
    for py_file in package_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = py_file.stem
        importlib.import_module(f".{module_name}", __package__)


def _extract_flattened_middleware(flat_config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Extract middleware config from flattened keys like middleware_static_directory."""
    middlewares: dict[str, dict[str, Any]] = {}
    prefix = "middleware_"

    for key, value in flat_config.items():
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix) :]
        if "_" not in rest:
            continue
        mw_name, param = rest.split("_", 1)
        if mw_name not in middlewares:
            middlewares[mw_name] = {}
        middlewares[mw_name][param] = value

    return [(name, config) for name, config in middlewares.items()]


def middleware_chain(
    middleware_config: str | list[str] | dict[str, Any],
    app: ASGIApp,
    full_config: Any = None,
) -> ASGIApp:
    """Build middleware chain from config with automatic ordering.

    Uses middleware_order class attribute for sorting (lower = earlier in chain).
    Uses middleware_default class attribute for default on/off state.

    YAML format:
        middleware:
          cors: on
          auth: on
          errors: on  # default=True, so usually omitted

        cors_middleware:
          allow_origins: "*"

        auth_middleware:
          bearer:
            reader_token:
              token: "tk_abc123"
              tags: "read"
          basic:
            admin:
              password: "secret"
              tags: "admin"

    Args:
        middleware_config: Dict {name: on/off}, comma-separated string, or list.
        app: The innermost ASGI app (usually Dispatcher).
        full_config: Full config object to lookup {name}_middleware sections.

    Returns:
        Wrapped ASGI app with middleware chain.
    """
    # Parse config into {name: enabled} dict
    config_dict: dict[str, bool] = {}

    if isinstance(middleware_config, str):
        # "cors, auth" -> all enabled
        for name in middleware_config.split(","):
            name = name.strip()
            if name:
                config_dict[name] = True
    elif hasattr(middleware_config, "as_dict"):
        # SmartOptions
        for name, value in middleware_config.as_dict().items():  # type: ignore[union-attr]
            config_dict[name] = _parse_enabled(value)
    elif isinstance(middleware_config, dict):
        for name, value in middleware_config.items():
            config_dict[name] = _parse_enabled(value)
    elif middleware_config:
        # List of names
        for name in middleware_config:
            config_dict[name] = True

    # Collect enabled middleware with their order
    enabled: list[tuple[int, str, type[BaseMiddleware]]] = []

    for name, cls in MIDDLEWARE_REGISTRY.items():
        # Check if enabled: config override or class default
        if name in config_dict:
            is_enabled = config_dict[name]
        else:
            is_enabled = cls.middleware_default

        if is_enabled:
            enabled.append((cls.middleware_order, name, cls))

    # Sort by order (lower first)
    enabled.sort(key=lambda x: x[0])

    # Build chain (reversed: first in order = outermost wrapper)
    for order, name, cls in reversed(enabled):
        config: Any = {}
        if full_config is not None:
            config_key = f"{name}_middleware"
            mw_config = full_config[config_key]
            if mw_config is not None:
                if hasattr(mw_config, "as_dict"):
                    config = mw_config.as_dict()
                else:
                    config = mw_config
        app = cls(app, **config)

    return app


def _parse_enabled(value: Any) -> bool:
    """Parse on/off/true/false value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("on", "true", "yes", "1")
    return bool(value)


_autodiscover()
globals().update(MIDDLEWARE_REGISTRY)

__all__ = [
    "BaseMiddleware",
    "MIDDLEWARE_REGISTRY",
    "headers_dict",
    "middleware_chain",
    *MIDDLEWARE_REGISTRY.keys(),
]
