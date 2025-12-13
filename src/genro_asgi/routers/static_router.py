# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""StaticRouter - Filesystem-backed router for serving static files.

Maps URL path selectors to filesystem paths. Implements RouterInterface
so it can be used wherever a router is expected (introspection, hierarchy).

The router returns file info dicts, not actual file content. The caller
(typically StaticSite or Dispatcher) is responsible for reading the file
and building the HTTP response.

Usage:
    router = StaticRouter(directory="./public")
    handler = router.get("css/style.css")
    if handler:
        file_info = handler()  # {"type": "file", "path": Path(...), ...}
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from genro_routes import RouterInterface

if TYPE_CHECKING:
    pass

__all__ = ["StaticRouter"]


class StaticRouter(RouterInterface):
    """Router that maps selectors to filesystem paths.

    Instead of method entries, resolves paths to files on disk.
    Subdirectories become child routers lazily.
    """

    __slots__ = ("directory", "name", "_html_index")

    def __init__(
        self,
        directory: str | Path,
        name: str | None = None,
        *,
        html_index: bool = True,
    ) -> None:
        self.directory = Path(directory)
        self.name = name
        self._html_index = html_index

    def get(self, selector: str, **options: Any) -> Callable:
        """Resolve selector to file handler.

        Args:
            selector: Path relative to directory (e.g., "index.html", "css/style.css")

        Returns:
            Callable handler that returns file info dict.

        Raises:
            FileNotFoundError: If file does not exist (404)
            PermissionError: If file is not readable (403)
        """
        if not selector or selector == "index":
            selector = "index.html" if self._html_index else ""

        if not selector:
            raise FileNotFoundError("No index file")

        path = (self.directory / selector).resolve()

        # Security: ensure path is within directory
        if not str(path).startswith(str(self.directory.resolve())):
            raise PermissionError("Path traversal not allowed")

        if not path.exists():
            raise FileNotFoundError(f"File not found: {selector}")

        if not path.is_file():
            raise FileNotFoundError(f"Not a file: {selector}")

        if not os.access(path, os.R_OK):
            raise PermissionError(f"Cannot read: {selector}")

        return self._make_file_handler(path)

    def _make_file_handler(self, path: Path) -> Callable:
        """Create handler that returns file info dict."""
        def handler(**kwargs: Any) -> dict[str, Any]:
            return {
                "type": "file",
                "path": path,
                "name": path.name,
                "suffix": path.suffix,
            }
        return handler

    def _on_attached_to_parent(self, parent: Any) -> None:
        """Called when attached to a parent router. No-op for static router."""
        pass

    def members(
        self, basepath: str | None = None, lazy: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """List files and directories as entries and routers."""
        if not self.directory.exists():
            return {}

        entries: dict[str, Any] = {}
        routers: dict[str, Any] = {}

        for item in self.directory.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_file():
                entries[item.name] = {
                    "name": item.name,
                    "type": "file",
                    "suffix": item.suffix,
                    "size": item.stat().st_size,
                }
            elif item.is_dir():
                child = StaticRouter(item, name=item.name, html_index=self._html_index)
                if lazy:
                    routers[item.name] = lambda c=child: c.members(lazy=True, **kwargs)
                else:
                    child_members = child.members(**kwargs)
                    if child_members:
                        routers[item.name] = child_members

        if not entries and not routers:
            return {}

        result: dict[str, Any] = {
            "name": self.name,
            "router": self,
            "directory": str(self.directory),
        }
        if entries:
            result["entries"] = entries
        if routers:
            result["routers"] = routers
        return result


if __name__ == "__main__":
    pass
