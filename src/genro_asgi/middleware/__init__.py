# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Middleware package - ASGI middleware for genro-asgi."""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send

MIDDLEWARE_REGISTRY: dict[str, type["BaseMiddleware"]] = {}


class BaseMiddleware(ABC):
    """Base class for all middleware. Subclasses auto-register via __init_subclass__.

    Optional: define `middleware_name` class attribute to use custom registry key.
    """

    __slots__ = ("app",)

    def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        self.app = app

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        name = getattr(cls, "middleware_name", cls.__name__)
        if name in MIDDLEWARE_REGISTRY:
            raise ValueError(f"Middleware name '{name}' already registered")
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
    middlewares: dict[str, dict[str, Any]] | list[tuple[str, dict[str, Any]]],
    app: ASGIApp,
) -> ASGIApp:
    """Build middleware chain from config.

    Supports two YAML formats (both produce same result via SmartOptions):

    Dict format (concise):
        middleware:
          logging:
            level: INFO
          cache: {}

    List format (explicit order):
        middleware:
          - type: logging
            level: INFO
          - type: cache

    Keys/type are middleware names (looked up in MIDDLEWARE_REGISTRY).
    Values are config dicts passed to middleware __init__.
    """
    # Convert SmartOptions to dict if needed
    if hasattr(middlewares, "as_dict"):
        middlewares = middlewares.as_dict()  # type: ignore[union-attr]

    # Handle dict format: {name: config, ...}
    if isinstance(middlewares, dict):
        items = list(middlewares.items())
    else:
        items = list(middlewares)

    # Build chain (reversed: last in config = innermost)
    for name, config in reversed(items):
        # Convert SmartOptions config to dict
        if hasattr(config, "as_dict"):
            config = config.as_dict()
        elif config is None:
            config = {}
        else:
            config = dict(config)  # Make a copy to avoid mutating original

        # Remove 'type' key if present (added by SmartOptions for list format)
        config.pop("type", None)

        # Resolve middleware class from registry
        # Try exact name first, then capitalized versions
        cls = MIDDLEWARE_REGISTRY.get(name)
        if cls is None:
            # Try CamelCase: "logging" -> "LoggingMiddleware"
            camel_name = name.title().replace("_", "") + "Middleware"
            cls = MIDDLEWARE_REGISTRY.get(camel_name)
        if cls is None:
            raise ValueError(
                f"Unknown middleware: {name}. " f"Available: {list(MIDDLEWARE_REGISTRY.keys())}"
            )

        app = cls(app, **config)
    return app


_autodiscover()
globals().update(MIDDLEWARE_REGISTRY)

__all__ = [
    "BaseMiddleware",
    "MIDDLEWARE_REGISTRY",
    "middleware_chain",
    *MIDDLEWARE_REGISTRY.keys(),
]
