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

"""Storage capability: filesystem storage as a mixin over the base server (§4, D6).

``StorageMixin`` is a capability composed over ``BaseServer`` (``class S(...,
StorageMixin, BaseServer)``). Unlike ``AuthMixin``/``SessionMixin`` it arms NO
middleware — storage is survival infrastructure, not a request-chain concern
(§4: PUBLIC = base + storage). Its cooperative ``__init__`` peels ``storage=``
and ``storage_key=`` and forwards everything else down the D16 chain.

``storage=`` shapes the ``LocalStorage`` the server owns:

- ``None`` → a fresh ``LocalStorage()`` (default ``base_dir``), only the
  predefined ``site``/``secure`` mounts;
- a ``LocalStorage`` instance → adopted as-is;
- a dict ``{mount_code: {"path": ..., "encrypted": ...}}`` → a fresh
  ``LocalStorage`` with one ``add_mount`` per entry.

``storage_key=`` installs at-rest encryption key material (``set_encryption_keys``
— comma-separated Fernet keys, first encrypts, all decrypt). Configured but
resolved empty is an explicit boot error (old-repo semantics: no silent
degradation); omitted, the encrypted mounts stay dormant until keys are set.

A composition WITHOUT the mixin has NO ``storage`` attribute at all.
"""

from __future__ import annotations

from typing import Any

from .storage import LocalStorage

__all__ = ["StorageMixin"]


class StorageMixin:
    """Storage capability mixin, composed over the base server. Arms no middleware.

    Constructor kwargs peeled here: ``storage`` — ``None`` (a fresh
    ``LocalStorage``), a ``LocalStorage`` instance (adopted), or a
    ``{code: {path, encrypted}}`` dict (mounts materialized); ``storage_key`` —
    the encryption key material (configured-but-empty raises).
    """

    def __init__(self, **kwargs: Any) -> None:
        storage: LocalStorage | dict[str, Any] | None = kwargs.pop("storage", None)
        storage_key: str | None = kwargs.pop("storage_key", None)
        super().__init__(**kwargs)
        self._storage = self._build_storage(storage)
        if storage_key is not None:
            if not storage_key:
                raise ValueError(
                    "'storage_key' is configured but resolved empty: the storage "
                    "encryption key is missing (check the environment)"
                )
            self._storage.set_encryption_keys(storage_key)

    def _build_storage(self, storage: LocalStorage | dict[str, Any] | None) -> LocalStorage:
        """Turn the ``storage=`` kwarg into the ``LocalStorage`` the server owns."""
        if storage is None:
            return LocalStorage()
        if isinstance(storage, LocalStorage):
            return storage
        built = LocalStorage()
        for code, mount_config in storage.items():
            built.add_mount(
                {
                    "name": code,
                    "type": "local",
                    "path": mount_config["path"],
                    "encrypted": bool(mount_config.get("encrypted")),
                }
            )
        return built

    @property
    def storage(self) -> LocalStorage:
        """The filesystem storage this server owns (mounts + at-rest encryption)."""
        return self._storage
