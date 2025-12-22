# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""StaticRouter - Filesystem-backed router for serving static files.

Maps URL paths to filesystem paths. Implements RouterInterface
so it can be used wherever a router is expected (introspection, hierarchy).

The router returns RouterNode with file handler. The handler returns file path,
and the caller (typically Dispatcher) is responsible for reading the file
and building the HTTP response.

Usage:
    router = StaticRouter(directory="./public")
    node = router.node("css/style.css")
    if node:
        file_path = node()  # Returns Path object
"""

from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from genro_routes import RouterInterface, RouterNode

if TYPE_CHECKING:
    pass

__all__ = ["StaticRouter"]


class StaticRouter(RouterInterface):
    """Router that maps paths to filesystem files.

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

    def node(self, path: str, **kwargs: Any) -> RouterNode:
        """Resolve path to file RouterNode.

        Args:
            path: Path relative to directory (e.g., "index.html", "css/style.css")

        Returns:
            RouterNode with callable that returns file Path.
            Empty RouterNode if file not found or not accessible.
        """
        selector = path
        if not selector or selector == "index":
            selector = "index.html" if self._html_index else ""

        if not selector:
            return RouterNode({})  # Empty node

        file_path = (self.directory / selector).resolve()

        # Security: ensure path is within directory
        if not str(file_path).startswith(str(self.directory.resolve())):
            return RouterNode({})  # Path traversal - return empty

        if not file_path.exists() or not file_path.is_file():
            return RouterNode({})  # Not found - return empty

        if not os.access(file_path, os.R_OK):
            return RouterNode({})  # Not readable - return empty

        return self._make_file_node(file_path, selector)

    def _make_file_node(self, file_path: Path, selector: str) -> RouterNode:
        """Create RouterNode for a file."""

        def handler(**kwargs: Any) -> Path:
            return file_path

        return RouterNode({
            "type": "entry",
            "name": file_path.name,
            "path": selector,
            "callable": handler,
            "doc": f"Static file: {file_path.name}",
            "metadata": {},
        }, router=self)  # type: ignore[arg-type]

    def _on_attached_to_parent(self, parent: Any) -> None:
        """Called when attached to a parent router. No-op for static router."""
        pass

    def values(self) -> Iterator[RouterInterface]:
        """Return iterator of child routers. For static router, yields nothing."""
        return iter(())

    def nodes(
        self,
        basepath: str | None = None,
        lazy: bool = False,
        mode: str | None = None,
        **kwargs: Any,
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
                    routers[item.name] = lambda c=child: c.nodes(lazy=True, **kwargs)
                else:
                    child_nodes = child.nodes(**kwargs)
                    if child_nodes:
                        routers[item.name] = child_nodes

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
