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

from .core import AuthCore

__all__ = ["AuthMixin"]


class AuthMixin:
    """Auth capability mixin, composed BEFORE the session/middleware/server classes.

    Constructor kwargs peeled here: ``auth`` — the credential config dict
    (``{'basic': ..., 'bearer': ..., 'jwt': [...]}``); ``None`` arms no header
    backend but still resolves the session identity through §5.5 precedence.
    """

    def __init__(self, **kwargs: Any) -> None:
        auth: dict[str, Any] | None = kwargs.pop("auth", None)
        middleware: dict[str, Any] = dict(kwargs.get("middleware") or {})
        middleware.setdefault("auth", True)
        kwargs["middleware"] = middleware
        super().__init__(**kwargs)
        self._auth_core = AuthCore(**(auth or {}))

    @property
    def auth_core(self) -> AuthCore:
        """The credential store backing this server's header authentication."""
        return self._auth_core

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
        return session.avatar if session is not None else None


if __name__ == "__main__":
    from ..application import BaseApplication
    from ..middleware import MiddlewareMixin
    from ..server import BaseServer
    from ..session import SessionMixin

    class DemoServer(AuthMixin, SessionMixin, MiddlewareMixin, BaseServer):
        pass

    server = DemoServer(
        primary=BaseApplication(),
        auth={"basic": {"admin": {"password": "secret", "tags": "admin"}}},
    )
    assert isinstance(server.auth_core, AuthCore)
    assert server.authenticate({"headers": []}) is None
    assert BaseServer(primary=BaseApplication()).authenticate({"headers": []}) is None
