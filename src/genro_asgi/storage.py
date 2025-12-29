# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""LocalStorage - Filesystem-only storage with genro-storage compatible API.

This module provides a minimal storage implementation that uses the same API
as genro-storage, but only supports local filesystem. When genro-storage
becomes available, simply change the import:

    # Before (local only)
    from genro_asgi.storage import LocalStorage

    # After (full genro-storage)
    from genro_storage import StorageManager as LocalStorage
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from smartasync import smartasync

__all__ = ["LocalStorage", "LocalStorageNode", "StorageNode"]


@runtime_checkable
class StorageNode(Protocol):
    """Abstract interface for storage nodes.

    Any storage backend (local, S3, HTTP) must implement this protocol.
    LocalStorageNode is the filesystem implementation.
    """

    @property
    def fullpath(self) -> str:
        """Return "mount:path" complete."""
        ...

    @property
    def path(self) -> str:
        """Return path without mount."""
        ...

    @property
    def exists(self) -> bool:
        """True if file/directory exists."""
        ...

    @property
    def isfile(self) -> bool:
        """True if it's a file."""
        ...

    @property
    def isdir(self) -> bool:
        """True if it's a directory."""
        ...

    @property
    def basename(self) -> str:
        """Filename with extension."""
        ...

    @property
    def mimetype(self) -> str:
        """MIME type based on extension."""
        ...

    def read_bytes(self) -> bytes:
        """Read content as bytes."""
        ...

    def read_text(self, encoding: str = "utf-8") -> str:
        """Read content as text."""
        ...

    def child(self, *parts: str) -> StorageNode:
        """Return a child node."""
        ...

    def children(self) -> list[StorageNode]:
        """List children if it's a directory."""
        ...


class LocalStorageNode:
    """Storage node for local filesystem. API compatible with genro_storage.StorageNode."""

    __slots__ = ("_storage", "_mount", "_path")

    def __init__(self, storage: LocalStorage, mount: str, path: str) -> None:
        self._storage = storage
        self._mount = mount
        self._path = path

    @property
    def fullpath(self) -> str:
        """Return "mount:path" complete."""
        return f"{self._mount}:{self._path}" if self._path else self._mount

    @property
    def path(self) -> str:
        """Return path without mount."""
        return self._path

    @property
    def _absolute_path(self) -> Path:
        """Absolute filesystem path (internal). Uses _resolve_mount for resolution."""
        base = self._storage._resolve_mount(self._mount)
        return base / self._path if self._path else base

    @property
    def exists(self) -> bool:
        """True if file/directory exists."""
        return self._absolute_path.exists()

    @property
    def isfile(self) -> bool:
        """True if it's a file."""
        return self._absolute_path.is_file()

    @property
    def isdir(self) -> bool:
        """True if it's a directory."""
        return self._absolute_path.is_dir()

    @property
    def size(self) -> int:
        """Size in bytes. 0 if doesn't exist."""
        path = self._absolute_path
        return path.stat().st_size if path.exists() and path.is_file() else 0

    @property
    def basename(self) -> str:
        """Filename with extension."""
        return Path(self._path).name if self._path else ""

    @property
    def suffix(self) -> str:
        """Extension with dot."""
        return Path(self._path).suffix if self._path else ""

    @property
    def ext(self) -> str:
        """Extension without dot."""
        suffix = self.suffix
        return suffix[1:] if suffix else ""

    @property
    def mimetype(self) -> str:
        """MIME type based on extension."""
        mime, _ = mimetypes.guess_type(self._path)
        return mime or "application/octet-stream"

    @property
    def parent(self) -> LocalStorageNode:
        """Return parent directory node."""
        parent_path = str(Path(self._path).parent)
        if parent_path == ".":
            parent_path = ""
        return LocalStorageNode(self._storage, self._mount, parent_path)

    @smartasync
    def read_bytes(self) -> bytes:
        """Read content as bytes."""
        return self._absolute_path.read_bytes()

    @smartasync
    def read_text(self, encoding: str = "utf-8") -> str:
        """Read content as text."""
        return self._absolute_path.read_text(encoding=encoding)

    @smartasync
    def read(self, mode: str = "r", encoding: str = "utf-8") -> str | bytes:
        """Read content. mode='r' for text, mode='rb' for binary."""
        if "b" in mode:
            return self._absolute_path.read_bytes()
        return self._absolute_path.read_text(encoding=encoding)

    @smartasync
    def write_bytes(self, data: bytes) -> bool:
        """Write bytes. Returns True if written."""
        path = self._absolute_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True

    @smartasync
    def write_text(self, text: str, encoding: str = "utf-8") -> bool:
        """Write text. Returns True if written."""
        path = self._absolute_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return True

    @smartasync
    def write(
        self, data: str | bytes, mode: str = "w", encoding: str = "utf-8"
    ) -> bool:
        """Write content. mode='w' for text, mode='wb' for binary."""
        if "b" in mode:
            if isinstance(data, str):
                data = data.encode(encoding)
            path = self._absolute_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return True
        if isinstance(data, bytes):
            data = data.decode(encoding)
        path = self._absolute_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding=encoding)
        return True

    def child(self, *parts: str) -> LocalStorageNode:
        """Return a child node."""
        child_path = "/".join([self._path, *parts]) if self._path else "/".join(parts)
        return LocalStorageNode(self._storage, self._mount, child_path)

    def children(self) -> list[LocalStorageNode]:
        """List children if it's a directory."""
        path = self._absolute_path
        if not path.is_dir():
            return []
        result = []
        mount_base = self._storage._resolve_mount(self._mount)
        for child in path.iterdir():
            child_rel = str(child.relative_to(mount_base))
            result.append(LocalStorageNode(self._storage, self._mount, child_rel))
        return result


class LocalStorage:
    """Storage manager filesystem-only. API compatible with genro_storage.StorageManager.

    Mount resolution order (see _resolve_mount):
    1. Method mount_{prefix}() → dynamic, overridable via subclass
    2. Dict _mounts → configured from config.yaml
    3. ValueError if not found
    """

    __slots__ = ("_mounts", "_base_dir")

    def __init__(self, base_dir: str | Path | None = None) -> None:
        """Create storage manager without configured mounts.

        Args:
            base_dir: Base directory for resolving relative paths. Defaults to cwd.
        """
        self._mounts: dict[str, Path] = {}
        self._base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()

    # ─────────────────────────────────────────────────────────────────
    # Predefined mount methods (dynamic, overridable via subclass)
    # ─────────────────────────────────────────────────────────────────

    def mount_site(self) -> Path:
        """Predefined mount: server base directory."""
        return self._base_dir

    # ─────────────────────────────────────────────────────────────────
    # Mount resolution
    # ─────────────────────────────────────────────────────────────────

    def _resolve_mount(self, prefix: str) -> Path:
        """Resolve a mount prefix to an absolute Path.

        Resolution order:
        1. Method mount_{prefix}() if exists → call it (dynamic)
        2. _mounts dict → configured mounts from add_mount/configure
        3. ValueError if not found

        Args:
            prefix: Mount name (e.g., "site", "session", "uploads")

        Returns:
            Absolute Path for the mount

        Raises:
            ValueError: if mount not found
        """
        # 1. Check for predefined method
        method = getattr(self, f"mount_{prefix}", None)
        if method is not None and callable(method):
            result = method()
            return Path(result) if not isinstance(result, Path) else result

        # 2. Check configured mounts
        if prefix in self._mounts:
            return self._mounts[prefix]

        raise ValueError(f"Mount '{prefix}' not found")

    def configure(self, source: str | list[dict[str, Any]]) -> None:
        """Configure mount points from list of dicts.

        Args:
            source: List of mount configurations

        Format:
            [{'name': 'site', 'type': 'local', 'path': '/path/to/dir'}]

        Note:
            Only type='local' is supported. Other types raise ValueError.
        """
        if isinstance(source, str):
            raise NotImplementedError("YAML/JSON file loading not implemented yet")
        for config in source:
            self.add_mount(config)

    def add_mount(self, config: dict[str, Any]) -> None:
        """Add a single mount point.

        Args:
            config: {'name': str, 'type': 'local', 'path': str}

        Raises:
            ValueError: if type != 'local'
            ValueError: if name already exists
        """
        name = config["name"]
        mount_type = config.get("type", "local")

        if mount_type != "local":
            raise ValueError(
                f"LocalStorage only supports type='local', got '{mount_type}'"
            )

        if name in self._mounts:
            raise ValueError(f"Mount '{name}' already exists")

        path = Path(config["path"])
        if not path.is_absolute():
            path = self._base_dir / path

        self._mounts[name] = path.resolve()

    def delete_mount(self, name: str) -> None:
        """Remove a mount point."""
        self._mounts.pop(name, None)

    def get_mount_names(self) -> list[str]:
        """List configured mount names."""
        return list(self._mounts.keys())

    def has_mount(self, name: str) -> bool:
        """True if mount exists (predefined method or configured)."""
        # Check predefined method first
        method = getattr(self, f"mount_{name}", None)
        if method is not None and callable(method):
            return True
        return name in self._mounts

    def _parse_mount_path(self, mount_or_path: str) -> tuple[str, str]:
        """Separate mount and path from "mount:path" string."""
        if ":" in mount_or_path:
            mount, path = mount_or_path.split(":", 1)
            return mount, path
        return mount_or_path, ""

    def node(
        self, mount_or_path: str | None = None, *path_parts: str
    ) -> LocalStorageNode:
        """Create a storage node.

        Args:
            mount_or_path: "mount:path" or just "mount"
            *path_parts: Additional path parts

        Returns:
            LocalStorageNode for the specified path

        Examples:
            storage.node('site:resources/logo.png')
            storage.node('site', 'resources', 'logo.png')
            storage.node('site:resources', 'images', 'logo.png')

        Raises:
            ValueError: if mount doesn't exist
        """
        if mount_or_path is None:
            raise ValueError("mount_or_path is required")

        mount, path = self._parse_mount_path(mount_or_path)

        # Validate mount exists (will raise ValueError if not)
        if not self.has_mount(mount):
            raise ValueError(f"Mount '{mount}' not found")

        # Combine path with additional parts
        if path_parts:
            if path:
                path = "/".join([path, *path_parts])
            else:
                path = "/".join(path_parts)

        return LocalStorageNode(self, mount, path)


if __name__ == "__main__":
    # Simple test
    storage = LocalStorage()
    storage.add_mount({"name": "test", "type": "local", "path": "/tmp"})
    node = storage.node("test:test_file.txt")
    print(f"fullpath: {node.fullpath}")
    print(f"exists: {node.exists}")
    print(f"mimetype: {node.mimetype}")
