# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""StaticRouter - Storage-backed router for serving static files.

Maps URL paths to storage nodes. Implements RouterInterface
so it can be used wherever a router is expected (introspection, hierarchy).

The router returns RouterNode with callable that returns StorageNode.
The caller (typically Dispatcher) uses the StorageNode to read content
and build the HTTP response.

Usage:
    # Create router from storage node
    router = StaticRouter(storage.node("site:static"))

    # Resolve a file
    router_node = router.node("css/style.css")
    if router_node:
        storage_node = router_node()  # Returns StorageNode
        content = storage_node.read_bytes()
        mime = storage_node.mimetype
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from genro_routes import RouterInterface, RouterNode

if TYPE_CHECKING:
    from genro_asgi.storage import StorageNode

__all__ = ["StaticRouter"]


class StaticRouter(RouterInterface):
    """Router backed by StorageNode. Returns RouterNode wrapping StorageNode.

    Dispatcher sees RouterInterface. The callable returns StorageNode
    which can be local filesystem, S3, HTTP, etc.
    """

    __slots__ = ("_root", "name", "_html_index")

    def __init__(
        self,
        root: StorageNode,
        name: str | None = None,
        *,
        html_index: bool = True,
    ) -> None:
        """Create a static file router from a StorageNode.

        Args:
            root: StorageNode pointing to directory to serve
            name: Router name for introspection
            html_index: If True, "index" resolves to "index.html"
        """
        self._root = root
        self.name = name
        self._html_index = html_index

    def node(self, path: str, **kwargs: Any) -> RouterNode:
        """Resolve path to RouterNode wrapping StorageNode.

        Args:
            path: Path relative to root (e.g., "index.html", "css/style.css")

        Returns:
            RouterNode with callable that returns StorageNode.
            Empty RouterNode if file not found.
        """
        selector = path
        if not selector or selector == "index":
            selector = "index.html" if self._html_index else ""

        if not selector:
            return RouterNode({})

        # Get child storage node
        storage_node = self._root.child(selector)

        if not storage_node.exists or not storage_node.isfile:
            return RouterNode({})

        return self._make_file_node(storage_node, selector)

    def _make_file_node(self, storage_node: StorageNode, selector: str) -> RouterNode:
        """Create RouterNode wrapping a StorageNode."""

        def handler(**kwargs: Any) -> StorageNode:
            return storage_node

        return RouterNode({
            "type": "entry",
            "name": storage_node.basename,
            "path": selector,
            "callable": handler,
            "doc": f"Static file: {storage_node.basename}",
            "metadata": {"mimetype": storage_node.mimetype},
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
        if not self._root.exists or not self._root.isdir:
            return {}

        entries: dict[str, Any] = {}
        routers: dict[str, Any] = {}

        for child in self._root.children():
            if child.basename.startswith("."):
                continue
            if child.isfile:
                entries[child.basename] = {
                    "name": child.basename,
                    "type": "file",
                    "mimetype": child.mimetype,
                }
            elif child.isdir:
                child_router = StaticRouter(child, name=child.basename, html_index=self._html_index)
                if lazy:
                    routers[child.basename] = lambda c=child_router: c.nodes(lazy=True, **kwargs)
                else:
                    child_nodes = child_router.nodes(**kwargs)
                    if child_nodes:
                        routers[child.basename] = child_nodes

        if not entries and not routers:
            return {}

        result: dict[str, Any] = {
            "name": self.name,
            "router": self,
            "root": self._root.fullpath,
        }
        if entries:
            result["entries"] = entries
        if routers:
            result["routers"] = routers
        return result


if __name__ == "__main__":
    pass
