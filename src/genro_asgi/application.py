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

"""App-side contract: the base class every mountable application extends.

``BaseApplication`` is what the server requires of an app (SPECIFICATION.md
§4, D7): an ASGI callable (``__call__`` implemented by concrete subclasses)
with an identity (``code``) and a placement (``mount``), a ``server``
property assigned exactly once by the owning server at attach time (ownership
channel, one direction — a second assignment raises ``RuntimeError``), and
lifecycle hooks ``on_startup``/``on_shutdown`` that subclasses may override
as sync OR async (the caller detects which at call time).

An application is a triplet **code + instance + mount**. ``code`` names it
(the key of ``server.applications``); ``mount`` is the URL prefix it answers
under, and ``""`` is the site root — a legitimate value, never a "missing"
one. Both are class attributes a subclass sets declaratively and a
constructor kwarg overrides per instance, so the same class can be installed
twice under different codes:

.. code-block:: python

    class Shop(RoutedApplication):
        mount = ""          # this app is a site root by design

    Shop(code="outlet", mount="outlet")

Cooperative init (D16): every class in the family implements
``__init__(self, **kwargs)``, peels ITS OWN kwargs and forwards the rest via
``super().__init__(**rest)``. Mixins go BEFORE the base in the MRO; this base
is the end of the chain and raises ``TypeError`` naming any leftover kwargs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .server import BaseServer
    from .types import Receive, Scope, Send

__all__ = ["BaseApplication"]


class BaseApplication:
    """Base class for applications attached to a ``BaseServer``.

    Constructor kwargs peeled here: ``code`` — the application's identity,
    empty meaning the class name lowercased — and ``mount`` — the URL prefix
    it answers under, ``None`` meaning the same as the code. Both default to
    the class attributes below, so a subclass can set them declaratively.
    """

    code: str = ""
    mount: str | None = None

    def __init__(self, **kwargs: Any) -> None:
        cls = type(self)
        code: str = kwargs.pop("code", cls.code) or cls.__name__.lower()
        mount: str | None = kwargs.pop("mount", cls.mount)
        self.code = code
        # ``is None`` and never truthiness: ``mount=""`` IS the site root, and
        # ``mount or code`` would silently move a root app to ``/code``.
        self.mount = code if mount is None else mount
        self._server: BaseServer | None = None
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(
                f"{type(self).__name__}.__init__() got unexpected keyword arguments: {unexpected}"
            )
        super().__init__()

    @property
    def server(self) -> BaseServer | None:
        """The server that owns this app (``None`` until attached)."""
        return self._server

    @server.setter
    def server(self, value: BaseServer) -> None:
        """Assign the owning server once; a second assignment raises ``RuntimeError``."""
        if self._server is not None:
            raise RuntimeError(f"{type(self).__name__} is already owned by a server")
        self._server = value

    def on_startup(self) -> None:
        """Lifecycle hook run at server startup. Override as sync or async."""

    def on_shutdown(self) -> None:
        """Lifecycle hook run at server shutdown. Override as sync or async."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point: concrete applications must implement it."""
        raise NotImplementedError(f"{type(self).__name__} does not implement the ASGI callable")
