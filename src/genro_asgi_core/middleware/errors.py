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

"""Error middleware: the outermost try/except of the chain.

``ErrorMiddleware`` (order 100, the only middleware enabled by default —
``errors=False`` disables it) maps control-flow exceptions to responses:
``Redirect`` → its status plus the ``Location`` header, ``HTTPException`` →
its status with the detail as body, any other ``Exception`` → 500 logged via
the instance logger. Responses are minimal hand-rolled ASGI (status +
``text/plain``) — the real Response class arrives in core 1c. The chain only
carries ``http`` scopes (the mixin routes the others past it), so no scope
filtering happens here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import HTTPException, Redirect
from .base import BaseMiddleware

if TYPE_CHECKING:
    from ..types import Receive, Scope, Send

__all__ = ["ErrorMiddleware"]


class ErrorMiddleware(BaseMiddleware):
    """Outermost middleware answering raised exceptions with HTTP responses."""

    middleware_order = 100
    middleware_default = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the chain; map ``Redirect``/``HTTPException``/``Exception`` to responses."""
        try:
            await self.app(scope, receive, send)
        except Redirect as exc:
            location = (b"location", exc.location.encode("latin-1"))
            await self._respond(send, exc.status, "", extra_headers=[location])
        except HTTPException as exc:
            await self._respond(send, exc.status, exc.detail or "")
        except Exception:
            self.logger.exception("unhandled error serving %s", scope.get("path", "?"))
            await self._respond(send, 500, "Internal Server Error")

    async def _respond(
        self,
        send: Send,
        status: int,
        text: str,
        extra_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        """Send a minimal ``text/plain`` ASGI response."""
        body = text.encode("utf-8")
        headers = [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body)).encode("latin-1")),
        ]
        if extra_headers:
            headers.extend(extra_headers)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    import asyncio

    from ..types import Message

    async def demo() -> None:
        async def raising_app(scope: Scope, receive: Receive, send: Send) -> None:
            raise HTTPException(404, "missing")

        async def receive() -> Message:
            return {"type": "http.request"}

        sent: list[Message] = []

        async def send(message: Message) -> None:
            sent.append(message)

        middleware = ErrorMiddleware(raising_app, None)
        await middleware({"type": "http", "path": "/"}, receive, send)
        assert sent[0]["status"] == 404
        assert sent[1]["body"] == b"missing"

    asyncio.run(demo())
