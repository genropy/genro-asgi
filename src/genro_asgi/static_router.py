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

    __slots__ = ("directory", "name", "_html_index", "_children")

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
        self._children: dict[str, StaticRouter] = {}

    def get(self, selector: str, **options: Any) -> Callable | StaticRouter | None:
        """Resolve selector to file handler or child router.

        Args:
            selector: Path relative to directory (e.g., "index.html", "css/style.css")

        Returns:
            - Callable handler if selector points to a file
            - StaticRouter if selector points to a directory
            - None if not found
        """
        if not selector or selector == "index":
            if self._html_index:
                index_path = self.directory / "index.html"
                if index_path.is_file():
                    return self._make_file_handler(index_path)
            return None

        if "/" in selector:
            parts = selector.split("/")
            first, rest = parts[0], "/".join(parts[1:])
            child = self._get_child_or_file(first)
            if isinstance(child, StaticRouter):
                return child.get(rest, **options)
            return None

        return self._get_child_or_file(selector)

    def _get_child_or_file(self, name: str) -> Callable | StaticRouter | None:
        """Get file handler or child router for a single path segment."""
        target = self.directory / name
        if target.is_file():
            return self._make_file_handler(target)
        if target.is_dir():
            return self._get_or_create_child(name, target)
        if self._html_index:
            html_target = self.directory / f"{name}.html"
            if html_target.is_file():
                return self._make_file_handler(html_target)
        return None

    def _get_or_create_child(self, name: str, path: Path) -> StaticRouter:
        """Get or create child router for subdirectory."""
        if name in self._children:
            return self._children[name]
        child = StaticRouter(
            path,
            name=name,
            html_index=self._html_index,
        )
        self._children[name] = child
        return child

    def _make_file_handler(self, path: Path) -> Callable:
        """Create handler that returns file info dict."""
        def handler() -> dict[str, Any]:
            return {
                "type": "file",
                "path": path,
                "name": path.name,
                "suffix": path.suffix,
            }
        return handler

    def members(
        self, basepath: str | None = None, lazy: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """List files and directories as entries and routers."""
        if basepath:
            target = self.get(basepath)
            if isinstance(target, StaticRouter):
                return target.members(lazy=lazy, **kwargs)
            return {}

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
                if lazy:
                    routers[item.name] = lambda p=item: StaticRouter(
                        p, name=item.name
                    ).members(lazy=True, **kwargs)
                else:
                    child = self._get_or_create_child(item.name, item)
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
