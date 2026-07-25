# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""LocalStorage — filesystem-only storage with a genro-storage compatible API.

This module provides a minimal storage implementation that uses the same API
as genro-storage, but only supports the local filesystem. When genro-storage
becomes available, simply change the import:

    # Before (local only)
    from genro_asgi.storage import LocalStorage

    # After (full genro-storage)
    from genro_storage import StorageManager as LocalStorage

The API is entirely SYNCHRONOUS (SPECIFICATION.md D22, core 1b ratified): the
node read/write methods do blocking I/O and return values directly. Async
callers on the server dispatch paths wrap them in ``server.run_sync()`` (the
Macro 1 dispatch protocol); there is no dual sync/async mode.

Each mount is a security boundary: a node path with an absolute segment, a
``..`` component, or resolving outside the mount base raises ``ValueError``
on access — no read/write/delete may ever touch a location outside its mount
root (D5 — explicit error, never a silent wrong-file access).

At-rest encryption
------------------
A mount can be encrypted: reads/writes on its nodes are transparently
decrypted/encrypted, so store contracts and clients above stay crypto-unaware.

    storage.set_encryption_keys("<key>[,<key2>,...]")   # install key material
    node = storage.node("secure:plugin_config.json")    # encrypted mount
    node.write_text('{"k": 1}')                          # ciphertext on disk
    node.read_text()                                     # plaintext back

Key material is one or more comma-separated Fernet keys wrapped in a
``MultiFernet``: the FIRST key encrypts, ALL keys decrypt (key rotation
without bulk migration). The keys live only in memory on the instance and are
never exposed; ``encryption_active`` reports whether they are installed.

The predefined ``secure`` mount (``<base_dir>/secure/``) is encrypted by
definition. A mount declared ``encrypted: True`` in ``add_mount`` is encrypted
too. There is no silent degradation (D5): using an encrypted mount without
installed keys, or finding a non-Fernet payload on one, raises explicitly —
never a plain-text fallback. Encryption is opt-in: without installed keys the
plain mounts behave exactly as before.
"""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from cryptography.fernet import Fernet, MultiFernet

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
    """Storage node for the local filesystem. API compatible with genro_storage.StorageNode."""

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
        """Absolute filesystem path (internal); a path escaping its mount raises.

        The mount is a security boundary: an absolute segment, a ``..``
        component, or a composed path resolving outside the mount base raises
        ``ValueError`` (D5 — explicit error, never a silent wrong-file access).
        Every read/write/delete/move/children flows through here.
        """
        base = self._storage._resolve_mount(self._mount)
        if not self._path:
            return base
        relative = Path(self._path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"path escapes mount '{self._mount}': {self._path}")
        candidate = base / self._path
        if not candidate.resolve().is_relative_to(base.resolve()):
            raise ValueError(f"path escapes mount '{self._mount}': {self._path}")
        return candidate

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

    @property
    def _encrypted(self) -> bool:
        """True when this node's mount encrypts at rest (via storage)."""
        return self._storage.mount_is_encrypted(self._mount)

    def _read_raw_bytes(self) -> bytes:
        """Read the file, decrypting first when the mount is encrypted."""
        data = self._absolute_path.read_bytes()
        return self._storage.decrypt(data) if self._encrypted else data

    def _write_raw_bytes(self, data: bytes) -> None:
        """Write the file, encrypting first when the mount is encrypted."""
        payload = self._storage.encrypt(data) if self._encrypted else data
        path = self._absolute_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def read_bytes(self) -> bytes:
        """Read content as bytes (decrypted on encrypted mounts)."""
        return self._read_raw_bytes()

    def read_text(self, encoding: str = "utf-8") -> str:
        """Read content as text (decrypted on encrypted mounts)."""
        return self._read_raw_bytes().decode(encoding)

    def read(self, mode: str = "r", encoding: str = "utf-8") -> str | bytes:
        """Read content. mode='r' for text, mode='rb' for binary."""
        data = self._read_raw_bytes()
        return data if "b" in mode else data.decode(encoding)

    def write_bytes(self, data: bytes) -> bool:
        """Write bytes (encrypted on encrypted mounts). Returns True if written."""
        self._write_raw_bytes(data)
        return True

    def write_text(self, text: str, encoding: str = "utf-8") -> bool:
        """Write text (encrypted on encrypted mounts). Returns True if written."""
        self._write_raw_bytes(text.encode(encoding))
        return True

    def write(self, data: str | bytes, mode: str = "w", encoding: str = "utf-8") -> bool:
        """Write content. mode='w' for text, mode='wb' for binary."""
        payload = data.encode(encoding) if isinstance(data, str) else data
        self._write_raw_bytes(payload)
        return True

    def delete(self) -> bool:
        """Remove this file. True if it was removed, False if it was absent.

        Only files are in scope; pointing at a directory is an explicit error
        (this API is for single-file stores, not tree removal).

        Raises:
            IsADirectoryError: if the node is an existing directory.
        """
        path = self._absolute_path
        if path.is_dir():
            raise IsADirectoryError(f"delete() targets a file, not a directory: {self.fullpath}")
        if not path.exists():
            return False
        path.unlink()
        return True

    def move_to(self, dest: LocalStorageNode) -> bool:
        """Move this node (file OR directory) to *dest*, atomically on one mount.

        The rename is a plain ``Path.rename`` — atomic when source and dest are on
        the same filesystem (the same mount), which is the spool's claim/settle
        guarantee. Encryption is at rest per byte: a move relocates the stored
        bytes untouched, so it is valid across same-encryption mounts. Creates the
        destination parent if missing.

        Raises:
            FileNotFoundError: if this node does not exist.
        """
        src = self._absolute_path
        if not src.exists():
            raise FileNotFoundError(f"move_to source does not exist: {self.fullpath}")
        dest_path = dest._absolute_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dest_path)
        return True

    def remove_tree(self) -> bool:
        """Remove this node recursively (a directory and everything under it).

        The tree-removal complement of ``delete()`` (which is file-only): removes a
        whole spool task folder in one call. True if something was removed, False if
        the node was absent. A plain file is removed too.
        """
        path = self._absolute_path
        if not path.exists():
            return False
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
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
    """Filesystem-only storage manager. API compatible with genro_storage.StorageManager.

    Mount resolution order (see _resolve_mount):
    1. Method mount_{prefix}() → dynamic, overridable via subclass
    2. Dict _mounts → registered via add_mount()/configure()
    3. ValueError if not found
    """

    __slots__ = ("_mounts", "_base_dir", "_encrypted_mounts", "_cipher")

    def __init__(self, base_dir: str | Path | None = None) -> None:
        """Create a storage manager without configured mounts.

        Args:
            base_dir: Base directory for resolving relative paths. Defaults to cwd.
        """
        self._mounts: dict[str, Path] = {}
        self._base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
        self._encrypted_mounts: set[str] = {"secure"}
        self._cipher: MultiFernet | None = None

    # ─────────────────────────────────────────────────────────────────
    # Predefined mount methods (dynamic, overridable via subclass)
    # ─────────────────────────────────────────────────────────────────

    def mount_site(self) -> Path:
        """Predefined mount: server base directory."""
        return self._base_dir

    def mount_secure(self) -> Path:
        """Predefined mount: server secure directory (encrypted at rest).

        The ``secure`` mount is encrypted by definition; using it requires
        installed key material (see ``set_encryption_keys``), else read/write
        raise explicitly (D5 — no plain-text fallback).
        """
        return self._base_dir / "secure"

    # ─────────────────────────────────────────────────────────────────
    # At-rest encryption
    # ─────────────────────────────────────────────────────────────────

    def set_encryption_keys(self, keys: str) -> None:
        """Install key material for encrypted mounts.

        ``keys`` is one or more comma-separated Fernet keys. They are wrapped
        in a ``MultiFernet``: the FIRST key encrypts, ALL keys decrypt (key
        rotation without bulk migration). The keys are held only in memory and
        never exposed.

        Args:
            keys: Comma-separated Fernet key(s), e.g. "<key>" or "<new>,<old>".

        Raises:
            ValueError: if no non-empty key is given.
        """
        parsed = [k.strip() for k in keys.split(",") if k.strip()]
        if not parsed:
            raise ValueError("set_encryption_keys: at least one key is required")
        self._cipher = MultiFernet([Fernet(k) for k in parsed])

    @property
    def encryption_active(self) -> bool:
        """True when key material is installed (read-only; keys stay hidden)."""
        return self._cipher is not None

    def mount_is_encrypted(self, name: str) -> bool:
        """True if the mount encrypts its content at rest."""
        return name in self._encrypted_mounts

    def encrypt(self, data: bytes) -> bytes:
        """Encrypt bytes with the installed cipher (first key encrypts).

        Raises:
            RuntimeError: if no key material is installed (D5).
        """
        if self._cipher is None:
            raise RuntimeError(
                "encrypted mount requires installed keys (set_encryption_keys)"
            )
        return self._cipher.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        """Decrypt bytes with the installed cipher (any key decrypts).

        Raises:
            RuntimeError: if no key material is installed (D5).
            cryptography.fernet.InvalidToken: on a non-Fernet payload (D5 — no
                plain-text fallback).
        """
        if self._cipher is None:
            raise RuntimeError(
                "encrypted mount requires installed keys (set_encryption_keys)"
            )
        return self._cipher.decrypt(token)

    # ─────────────────────────────────────────────────────────────────
    # Mount resolution
    # ─────────────────────────────────────────────────────────────────

    @property
    def mounts(self) -> dict[str, Path]:
        """The live dict of configured mounts (code → absolute Path).

        Predefined mounts (``mount_*`` methods) are resolved dynamically and are
        NOT listed here; this is the mapping populated by ``add_mount``.
        """
        return self._mounts

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
        """Configure mount points from a list of dicts.

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
            config: {'name': str, 'type': 'local', 'path': str, 'encrypted': bool}
                ``encrypted`` (default False) makes the mount encrypt at rest;
                accessing it then requires installed keys (set_encryption_keys).

        Raises:
            ValueError: if type != 'local'
            ValueError: if name already exists
        """
        name = config["name"]
        mount_type = config.get("type", "local")

        if mount_type != "local":
            raise ValueError(f"LocalStorage only supports type='local', got '{mount_type}'")

        if name in self._mounts:
            raise ValueError(f"Mount '{name}' already exists")

        path = Path(config["path"])
        if not path.is_absolute():
            path = self._base_dir / path

        self._mounts[name] = path.resolve()
        if config.get("encrypted"):
            self._encrypted_mounts.add(name)

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
        """Separate mount and path from a "mount:path" string."""
        if ":" in mount_or_path:
            mount, path = mount_or_path.split(":", 1)
            return mount, path
        return mount_or_path, ""

    def node(self, mount_or_path: str | None = None, *path_parts: str) -> LocalStorageNode:
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
