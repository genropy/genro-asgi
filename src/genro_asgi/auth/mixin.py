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

"""Auth capability: header/session identity resolution as a mixin (D16).

``AuthMixin`` is composed BEFORE ``SessionMixin``/``MiddlewareMixin``/
``BaseServer`` (``class S(AuthMixin, SessionMixin, MiddlewareMixin,
BaseServer)``). Its cooperative ``__init__`` peels ``auth=`` (the config dict;
``None`` builds an ``AuthCore`` with no header backends armed) and ARMS
``AuthMiddleware`` by injecting ``{"auth": True}`` into the ``middleware`` config
it forwards along the cooperative chain — the same mechanism ``SessionMixin``
uses, so composing the mixins arms header auth with no user action while an
explicit ``middleware={"auth": False}`` still wins.

It also wires the server's identity stores. ``users=`` and ``tokens=`` each take
a config dict (``{mount, prefix}``, defaulting to ``site:users`` /
``site:api_keys``) OR a ready store instance; ``admin_password=`` seeds the
bootstrap admin. The stores are built AFTER ``super().__init__()`` returns — by
then the cooperative chain has run and ``self.storage`` exists, since AuthMixin
precedes StorageMixin in the MRO. The ``user_store`` / ``api_key_store``
properties return ``None`` when unconfigured (the shape ``login`` already reads).
A config dict without storage on the server is a boot error (no silent fallback);
a ready instance needs no storage. ``admin_password`` with no ``users=`` config
implies the default users store. The bootstrap admin is an UPSERT at boot (config
wins): runtime edits to the admin record do not survive a reboot.

It overrides the §4 contract method ``authenticate(request)`` with the §5.5
identity precedence: an ``Authorization`` header wins (API-first) — its
``AuthCore`` verdict is an ``Avatar`` or a raised ``HTTPUnauthorized``; with no
header the request's session avatar is used. "Nobody" is ``None`` uniformly:
an anonymous session carries ``avatar is None`` and ``self.session(request)``
returns ``None`` unchanged when ``SessionMixin`` is absent, so the precedence
degrades to ``None`` in both cases. In the middleware chain
``SessionMiddleware`` (order 400) runs OUTSIDE ``AuthMiddleware`` (order 450),
so the session is already on the scope when the fallback runs.
"""

from __future__ import annotations

from typing import Any

from .api_key_store import ApiKeyStore, FileApiKeyStore
from .core import AuthCore
from .user_store import FileUserStore, UserStore

__all__ = ["AuthMixin"]

ADMIN_IDENTITY = "admin"
ADMIN_TAGS = ["SUPERADMIN"]


class AuthMixin:
    """Auth capability mixin, composed BEFORE the session/middleware/server classes.

    Constructor kwargs peeled here: ``auth`` — the credential config dict
    (``{'basic': ..., 'bearer': ..., 'jwt': [...]}``); ``None`` arms no header
    backend but still resolves the session identity through §5.5 precedence.
    ``users`` / ``tokens`` — a ``{mount, prefix}`` config dict or a ready store
    instance for the identity/api-key stores; ``admin_password`` — the bootstrap
    admin's password (implies the default users store when ``users`` is absent).
    """

    def __init__(self, **kwargs: Any) -> None:
        auth: dict[str, Any] | None = kwargs.pop("auth", None)
        users = kwargs.pop("users", None)
        tokens = kwargs.pop("tokens", None)
        admin_password: str | None = kwargs.pop("admin_password", None)
        middleware: dict[str, Any] = dict(kwargs.get("middleware") or {})
        middleware.setdefault("auth", True)
        kwargs["middleware"] = middleware
        super().__init__(**kwargs)
        if users is None and admin_password is not None:
            users = {}
        self._user_store = self._build_user_store(users)
        self._api_key_store = self._build_api_key_store(tokens)
        self._auth_core = AuthCore(**(auth or {}), api_key_store=self._api_key_store)
        if admin_password is not None:
            self._bootstrap_admin(admin_password)

    @property
    def auth_core(self) -> AuthCore:
        """The credential store backing this server's header authentication."""
        return self._auth_core

    @property
    def user_store(self) -> UserStore | None:
        """The local identity store, or ``None`` when no ``users`` is configured."""
        return self._user_store

    @property
    def api_key_store(self) -> ApiKeyStore | None:
        """The api-key registry, or ``None`` when no ``tokens`` is configured."""
        return self._api_key_store

    def _build_user_store(self, users: Any) -> UserStore | None:
        """Build the user store from a config dict, pass through an instance, or None."""
        if users is None:
            return None
        if isinstance(users, UserStore):
            return users
        return FileUserStore(self._require_storage("users"), **users)

    def _build_api_key_store(self, tokens: Any) -> ApiKeyStore | None:
        """Build the api-key store from a config dict, pass through an instance, or None."""
        if tokens is None:
            return None
        if isinstance(tokens, ApiKeyStore):
            return tokens
        return FileApiKeyStore(self._require_storage("tokens"), **tokens)

    def _require_storage(self, section: str) -> Any:
        """Return the server storage, or raise when a config-dict store needs it.

        A ``{mount, prefix}`` store cannot be built without a StorageMixin on the
        server: an incoherent configuration is a boot error, never a silent None.
        """
        storage = getattr(self, "storage", None)
        if storage is None:
            raise RuntimeError(
                f"'{section}' store needs a storage mount, but the server has no storage"
            )
        return storage

    def _bootstrap_admin(self, admin_password: str) -> None:
        """UPSERT the bootstrap admin at boot (config wins over any stored record)."""
        store = self._user_store
        store.save(
            {
                "identity": ADMIN_IDENTITY,
                "password_hash": store.hash_password(admin_password),
                "tags": list(ADMIN_TAGS),
                "enabled": True,
            }
        )

    def authenticate(self, request: Any) -> Any:
        """Resolve the request identity: header credentials win, else the session.

        The ``Authorization`` header is API-first — a valid credential yields an
        ``Avatar``, an invalid one raises ``HTTPUnauthorized`` (no fallback).
        Without a header, the session avatar is returned (``None`` when no
        session capability is composed or the session is anonymous).
        """
        avatar = self.auth_core.authenticate(request)
        if avatar is not None:
            return avatar
        session = self.session(request)
        return session.avatar() if session is not None else None
