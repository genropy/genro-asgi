# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""StaticSite - Application for serving static files.

A minimal app that uses StaticRouter to serve files from disk.
Can be mounted on AsgiServer like any other app.

Config in YAML:
    apps:
      docs:
        module: "genro_asgi:StaticSite"
        directory: "./public"
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .base import AsgiApplication
from ..static_router import StaticRouter

if TYPE_CHECKING:
    pass

__all__ = ["StaticSite"]


class StaticSite(AsgiApplication):
    """Application that serves static files from a directory."""

    __slots__ = ("directory", "name", "router", "_routers")

    def __init__(self, directory: str | Path, name: str = "static") -> None:
        self.directory = Path(directory)
        self.name = name
        self.router = StaticRouter(self.directory, name=name)
        self._routers = {"router": self.router}

    def get(self, selector: str, **options: Any) -> Any:
        """Delegate to router."""
        return self.router.get(selector, **options)

    def members(self, **kwargs: Any) -> dict[str, Any]:
        """Delegate to router."""
        return self.router.members(**kwargs)


if __name__ == "__main__":
    pass
