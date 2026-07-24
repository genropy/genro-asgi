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
with a ``mount_name`` (constructor kwarg, empty for a primary), a ``server``
property assigned exactly once by the owning server at attach time (ownership
channel, one direction — a second assignment raises ``RuntimeError``), and
lifecycle hooks ``on_startup``/``on_shutdown`` that subclasses may override
as sync OR async (the caller detects which at call time).

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

    Constructor kwargs peeled here: ``mount_name`` — the URL prefix under
    which a server mounts this app as a secondary (empty for a primary).
    """

    def __init__(self, **kwargs: Any) -> None:
        self._mount_name: str = kwargs.pop("mount_name", "")
        self._server: BaseServer | None = None
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(
                f"{type(self).__name__}.__init__() got unexpected keyword arguments: {unexpected}"
            )
        super().__init__()

    @property
    def mount_name(self) -> str:
        """URL prefix under which this app is mounted (empty for a primary)."""
        return self._mount_name

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


if __name__ == "__main__":
    app = BaseApplication(mount_name="demo")
    assert app.mount_name == "demo"
    assert app.server is None
