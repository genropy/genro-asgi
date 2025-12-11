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
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        ...


def _autodiscover() -> None:
    """Import all middleware modules in this package to trigger registration."""
    package_dir = Path(__file__).parent
    for py_file in package_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = py_file.stem
        importlib.import_module(f".{module_name}", __package__)


def build_middleware_chain(
    app: ASGIApp, middlewares: list[tuple[type | str, dict[str, Any]]]
) -> ASGIApp:
    """Build middleware chain from list of (class_or_name, config) tuples."""
    for cls_or_name, config in reversed(middlewares):
        if isinstance(cls_or_name, str):
            if cls_or_name not in MIDDLEWARE_REGISTRY:
                raise ValueError(f"Unknown middleware: {cls_or_name}")
            cls_or_name = MIDDLEWARE_REGISTRY[cls_or_name]
        app = cls_or_name(app, **config)
    return app


_autodiscover()

__all__ = ["BaseMiddleware"]
