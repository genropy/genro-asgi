# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""StaticSite application class."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..base import AsgiApplication
from ...routers import StaticRouter

__all__ = ["StaticSite"]


class StaticSite(AsgiApplication):
    """Application that serves static files from a directory.

    Config in YAML (as path-based app):
        apps:
          docs:
            path: "./my_static_site"

    Where ./my_static_site/config.yaml contains:
        directory: "./public"
        name: "docs"
    """

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
    site = StaticSite(".")
    print(site)
