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
its status with the detail as ``text/plain`` body, any other ``Exception`` →
500 logged via the instance logger. Responses are built with the ``Response``
class; an exception's ``headers`` (e.g. a ``WWW-Authenticate`` challenge) are
forwarded onto the response.

The middleware wraps ``send`` to track whether ``http.response.start`` has
already passed downstream: an exception raised AFTER the response started
cannot be answered (a second start would corrupt the stream), so it is logged
and re-raised — the server/transport tears the connection down. The chain only
carries ``http`` scopes (the mixin routes the others past it), so no scope
filtering happens here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import HTTPException, Redirect
from ..response import Response
from .base import BaseMiddleware

if TYPE_CHECKING:
    from ..types import Message, Receive, Scope, Send

__all__ = ["ErrorMiddleware"]


class ErrorMiddleware(BaseMiddleware):
    """Outermost middleware answering raised exceptions with HTTP responses."""

    middleware_order = 100
    middleware_default = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the chain; map raised exceptions to responses unless already started."""
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:
                self.logger.exception(
                    "error after response started serving %s", scope.get("path", "?")
                )
                raise
            response = self._error_response(exc, scope)
            await response(scope, receive, send)

    def _error_response(self, exc: Exception, scope: Scope) -> Response:
        """Build the ``Response`` for a raised exception, forwarding its headers."""
        if isinstance(exc, Redirect):
            response = Response(status_code=exc.status, media_type="text/plain")
            response.set_header("location", exc.location)
        elif isinstance(exc, HTTPException):
            response = Response(
                content=exc.detail or "", status_code=exc.status, media_type="text/plain"
            )
        else:
            self.logger.exception("unhandled error serving %s", scope.get("path", "?"))
            return Response(
                content="Internal Server Error", status_code=500, media_type="text/plain"
            )
        for name, value in exc.headers:
            response.set_header(name.decode("latin-1"), value.decode("latin-1"))
        return response


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
