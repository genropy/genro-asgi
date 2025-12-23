# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""StaticRouter - Storage-backed router with best-match path resolution.

Maps URL paths to storage nodes (files or directories). Uses best-match
strategy: walks the path as far as possible, returns the deepest valid
node with unconsumed segments as extra_args.

Implements RouterInterface for use in routing hierarchies.

Best-Match Resolution:
    Given path "alfa/beta/gamma/123?xx=3" and filesystem with only alfa/beta/:

    1. Walk: alfa (exists) → beta (exists) → gamma (not found) → STOP
    2. Return: RouterNode pointing to alfa/beta/
    3. extra_args: ["gamma", "123"]
    4. partial_kwargs: {"xx": "3"}

    The caller decides what to do with extra_args (e.g., pass to handler,
    use for sub-routing, return 404, etc.)

Usage:
    # Create router from storage node
    router = StaticRouter(storage.node("site:static"))

    # Resolve exact file
    router_node = router.node("css/style.css")
    storage_node = router_node()          # StorageNode for style.css
    content = storage_node.read_bytes()

    # Resolve with best-match (partial path)
    router_node = router.node("docs/api/v2/users?format=json")
    # If only docs/api/ exists:
    storage_node = router_node()          # StorageNode for docs/api/
    extra = router_node.extra_args        # ["v2", "users"]
    params = router_node.partial_kwargs   # {"format": "json"}

    # Check node type
    if router_node.metadata["isfile"]:
        # Serve file content
        pass
    elif router_node.metadata["isdir"]:
        # Directory - caller decides (list, index.html, pass to handler)
        pass

RouterNode Attributes:
    - type: "entry" (file) or "router" (directory)
    - name: basename of the storage node
    - path: resolved path (consumed segments)
    - callable: function returning StorageNode
    - extra_args: list of unconsumed path segments
    - partial_kwargs: dict from parsed query string
    - metadata: {"mimetype": str, "isdir": bool, "isfile": bool}
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from genro_routes import RouterInterface, RouterNode

if TYPE_CHECKING:
    from genro_asgi.storage import StorageNode

__all__ = ["StaticRouter"]


class StaticRouter(RouterInterface):
    """Storage-backed router with best-match resolution.

    Wraps a StorageNode (filesystem, S3, HTTP, etc.) and resolves paths
    using best-match strategy. Returns RouterNode whose callable yields
    the underlying StorageNode.

    Attributes:
        name: Router name for introspection (optional)
    """

    __slots__ = ("_root", "name", "_html_index")

    def __init__(
        self,
        root: StorageNode,
        name: str | None = None,
        *,
        html_index: bool = True,
    ) -> None:
        """Initialize router with a storage root.

        Args:
            root: StorageNode pointing to the directory to serve.
            name: Optional name for introspection and debugging.
            html_index: Reserved for future use (index.html resolution).
        """
        self._root = root
        self.name = name
        self._html_index = html_index

    def node(self, path: str, **kwargs: Any) -> RouterNode:
        """Resolve path using best-match strategy.

        Walks path segment by segment until a non-existent node is found.
        Returns the deepest valid node with unconsumed segments in extra_args.

        Args:
            path: Relative path, optionally with query string.
                  Examples: "css/style.css", "api/v2/users?limit=10"

        Returns:
            RouterNode with:
            - callable() → StorageNode (the resolved file or directory)
            - extra_args: list of path segments after the resolved node
            - partial_kwargs: dict parsed from query string
            - type: "entry" (file) or "router" (directory)
            - metadata: {"mimetype", "isdir", "isfile"}

            Empty RouterNode (callable=None) if root doesn't exist.

        Examples:
            # Exact file match
            node = router.node("style.css")
            node.extra_args      # []
            node()               # StorageNode for style.css

            # Partial match with extra segments
            node = router.node("docs/api/v2/users")
            # If only docs/api/ exists:
            node.extra_args      # ["v2", "users"]
            node()               # StorageNode for docs/api/

            # With query string
            node = router.node("data?format=json&limit=10")
            node.partial_kwargs  # {"format": "json", "limit": "10"}
        """
        # Parse query string if present
        query_kwargs: dict[str, str] = {}
        if "?" in path:
            path, query_string = path.split("?", 1)
            query_kwargs = self._parse_query_string(query_string)

        # Normalize path
        path = path.strip("/")
        if not path:
            # Root requested
            if self._root.exists:
                return self._make_node(self._root, "", [], query_kwargs)
            return RouterNode({})

        # Split into segments
        segments = path.split("/")

        # Best-match: walk path tracking last valid node
        current_node = self._root
        last_valid_node = self._root if self._root.exists else None
        last_valid_index = -1  # -1 means root itself

        for i, segment in enumerate(segments):
            child = current_node.child(segment)
            if child.exists:
                current_node = child
                last_valid_node = child
                last_valid_index = i
            else:
                # Can't go further
                break

        if last_valid_node is None:
            return RouterNode({})

        # Calculate extra_args (unconsumed segments)
        if last_valid_index == -1:
            extra_args = segments
            resolved_path = ""
        else:
            extra_args = segments[last_valid_index + 1:]
            resolved_path = "/".join(segments[: last_valid_index + 1])

        return self._make_node(last_valid_node, resolved_path, extra_args, query_kwargs)

    def _parse_query_string(self, query_string: str) -> dict[str, str]:
        """Parse query string into dict. Last value wins for duplicate keys."""
        result: dict[str, str] = {}
        for pair in query_string.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                result[key] = value
            elif pair:
                result[pair] = ""  # Flag-style param: "?debug" → {"debug": ""}
        return result

    def _make_node(
        self,
        storage_node: StorageNode,
        resolved_path: str,
        extra_args: list[str],
        query_kwargs: dict[str, str],
    ) -> RouterNode:
        """Create RouterNode wrapping a StorageNode.

        Args:
            storage_node: The resolved StorageNode (file or directory).
            resolved_path: Path consumed during resolution (e.g., "docs/api").
            extra_args: Unconsumed path segments (e.g., ["v2", "users"]).
            query_kwargs: Parsed query string parameters.

        Returns:
            RouterNode with type="entry" for files, "router" for directories.
            The callable returns the storage_node unchanged.
        """
        node_type = "entry" if storage_node.isfile else "router"

        def handler(*args: Any, **kw: Any) -> StorageNode:
            # RouterNode.__call__ prepends extra_args to args.
            # We ignore them here - caller reads extra_args directly.
            return storage_node

        return RouterNode(
            {
                "type": node_type,
                "name": storage_node.basename or self.name or "root",
                "path": resolved_path,
                "callable": handler,
                "extra_args": extra_args,
                "partial_kwargs": query_kwargs,
                "doc": f"Storage: {storage_node.basename}",
                "metadata": {
                    "mimetype": storage_node.mimetype,
                    "isdir": storage_node.isdir,
                    "isfile": storage_node.isfile,
                },
            },
            router=self,
        )


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
        pattern: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return a tree of files/directories respecting filters.

        Args:
            basepath: Path to start from (e.g., "images/icons").
                      If provided, returns nodes starting from that point.
            lazy: If True, child directories are returned as callables
                  instead of recursively expanded.
            mode: Output format mode (reserved for compatibility).
            pattern: Regex pattern to filter entry names.
                     Only files whose name matches are included.

        Returns:
            Dict with keys: name, description, router, entries, routers.
            Empty dict if root doesn't exist or is empty.
        """
        # Handle basepath navigation
        if basepath:
            target_node = self.node(basepath)
            if not target_node or target_node.type != "router":
                return {}
            # Get the storage node and create a new router for it
            storage_node = target_node()
            target_router = StaticRouter(
                storage_node, name=storage_node.basename, html_index=self._html_index
            )
            return target_router.nodes(lazy=lazy, mode=mode, pattern=pattern, **kwargs)

        if not self._root.exists or not self._root.isdir:
            return {}

        # Compile pattern once if provided
        pattern_re = re.compile(pattern) if pattern else None

        entries: dict[str, Any] = {}
        routers: dict[str, Any] = {}

        for child in self._root.children():
            if child.basename.startswith("."):
                continue
            if child.isfile:
                # Apply pattern filter to files
                if pattern_re is None or pattern_re.search(child.basename):
                    entries[child.basename] = self._entry_info(child)
            elif child.isdir:
                child_router = StaticRouter(
                    child, name=child.basename, html_index=self._html_index
                )
                if lazy:
                    # In lazy mode, return router reference
                    routers[child.basename] = child_router
                else:
                    child_nodes = child_router.nodes(pattern=pattern, **kwargs)
                    if child_nodes:
                        routers[child.basename] = child_nodes

        if not entries and not routers:
            return {}

        result: dict[str, Any] = {
            "name": self.name,
            "description": f"Static files from {self._root.fullpath}",
            "router": self,
        }
        if entries:
            result["entries"] = entries
        if routers:
            result["routers"] = routers
        return result

    def _entry_info(self, storage_node: StorageNode) -> dict[str, Any]:
        """Return entry info dict for a file."""
        return {
            "name": storage_node.basename,
            "type": "entry",
            "mimetype": storage_node.mimetype,
            "metadata": {
                "size": getattr(storage_node, "size", None),
                "fullpath": storage_node.fullpath,
            },
        }


if __name__ == "__main__":
    pass
