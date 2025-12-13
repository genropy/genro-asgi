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

    __slots__ = ("directory", "name", "index", "router", "_routers")

    def __init__(
        self,
        directory: str | Path,
        name: str = "static",
        index: str = "index.html",
        app_dir: str | Path | None = None,
    ) -> None:
        directory_path = Path(directory)
        if app_dir and not directory_path.is_absolute():
            directory_path = Path(app_dir) / directory_path
        self.directory = directory_path.resolve()
        self.name = name
        self.index = index
        self.router = StaticRouter(self.directory, name=name, html_index=bool(index))
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
