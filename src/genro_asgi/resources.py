# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ResourceLoader - Hierarchical resource loading with fallback.

Loads resources from the routing tree with fallback from specific to general.
Uses LocalStorage for filesystem access.

Invariant "dove + cosa = costante":
For /_resource/shop/tables/article?name=assets/logo.png:

| Level   | Where (resources/)              | What (name)                          |
|---------|---------------------------------|--------------------------------------|
| article | article/resources/              | assets/logo.png                      |
| tables  | tables/resources/               | article/assets/logo.png              |
| shop    | shop/resources/                 | tables/article/assets/logo.png       |
| server  | server/resources/               | shop/tables/article/assets/logo.png  |

Composition strategies:
- Override (images, HTML, JSON): first found wins (most specific)
- Merge (CSS, JS): concatenate all (general to specific)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .storage import LocalStorageNode

__all__ = ["ResourceLoader"]

MERGE_EXTENSIONS = {".css", ".js"}


class ResourceLoader:
    """Loads resources with hierarchical fallback along the routing tree."""

    __slots__ = ("server",)

    def __init__(self, server: Any) -> None:
        self.server = server

    def collect_levels(self, args: tuple[str, ...]) -> list[Any]:
        """Collect routing levels from path segments.

        Walks the routing tree and collects instances that may have resources.

        Args:
            args: Path segments (e.g., ("shop", "tables", "article"))

        Returns:
            List of instances (server, apps, routing classes) from root to leaf
        """
        levels = [self.server]
        current = self.server.router

        for segment in args:
            # Try to get child router/instance
            child = current.get(segment) if hasattr(current, "get") else None
            if child is None:
                break

            # If child has an instance (app or routing class), add it
            if hasattr(child, "instance") and child.instance is not None:
                levels.append(child.instance)

            current = child

        return levels

    def get_resources_node(self, level: Any) -> LocalStorageNode | None:
        """Get the resources storage node for a level.

        Args:
            level: Server, app, or routing class instance

        Returns:
            StorageNode for resources/ directory, or None if not found
        """
        # Get resources_path from level (property or attribute)
        resources_path = getattr(level, "resources_path", None)
        if resources_path is None:
            return None

        # resources_path should be a Path or string
        if not isinstance(resources_path, (str, Path)):
            return None

        path = Path(resources_path)
        if not path.is_dir():
            return None

        # Create a storage node for this path
        # Use server's storage with a dynamic mount
        storage = self.server.storage
        mount_name = f"_resources_{id(level)}"

        # Add temporary mount if not exists
        if not storage.has_mount(mount_name):
            storage.add_mount({
                "name": mount_name,
                "type": "local",
                "path": str(path),
            })

        node: LocalStorageNode = storage.node(mount_name)
        return node

    def find_candidates(
        self,
        levels: list[Any],
        args: tuple[str, ...],
        name: str,
    ) -> list[LocalStorageNode]:
        """Find resource candidates using the invariant.

        Args:
            levels: List of routing levels (server to leaf)
            args: Original path segments
            name: Resource name to find

        Returns:
            List of StorageNodes that exist, from most specific to most general
        """
        candidates = []
        segments = list(args)

        # Start from most specific (last level) to most general (server)
        accumulated = name

        for i, level in enumerate(reversed(levels)):
            resources_node = self.get_resources_node(level)

            if resources_node is not None:
                # Try to find the resource at this level
                resource = resources_node.child(accumulated)
                if resource.exists and resource.isfile:
                    candidates.append(resource)

            # Prepend segment for next level up
            level_index = len(levels) - 1 - i
            if level_index > 0 and level_index <= len(segments):
                segment = segments[level_index - 1]
                accumulated = f"{segment}/{accumulated}"

        return candidates

    def compose(
        self,
        candidates: list[LocalStorageNode],
        name: str,
    ) -> tuple[bytes, str]:
        """Compose resource response from candidates.

        Args:
            candidates: List of StorageNodes (most specific first)
            name: Original resource name (for extension detection)

        Returns:
            Tuple of (content_bytes, mime_type)
        """
        ext = Path(name).suffix.lower()

        if ext in MERGE_EXTENSIONS:
            # Merge: concatenate all from general to specific
            content = b""
            for node in reversed(candidates):
                content += node.read_bytes() + b"\n"
            mime_type = "text/css" if ext == ".css" else "application/javascript"
        else:
            # Override: use most specific (first candidate)
            node = candidates[0]
            content = node.read_bytes()
            mime_type = node.mimetype

        return content, mime_type

    def load(
        self,
        *args: str,
        name: str,
    ) -> tuple[bytes, str] | None:
        """Load resource with hierarchical fallback.

        Args:
            *args: Path segments in routing tree
            name: Resource name to load

        Returns:
            Tuple (content_bytes, mime_type) or None if not found.
            Composition (override vs merge) is handled internally.
        """
        levels = self.collect_levels(args)
        candidates = self.find_candidates(levels, args, name)

        if not candidates:
            return None

        return self.compose(candidates, name)


if __name__ == "__main__":
    pass
