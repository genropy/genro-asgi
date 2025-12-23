# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Error Handling Middleware."""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

from . import BaseMiddleware
from ..exceptions import HTTPException, Redirect

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class ErrorMiddleware(BaseMiddleware):
    """Error handling middleware - catches exceptions and returns error responses.

    Handles HTTPException (returns status/detail), Redirect (302), and generic
    exceptions (500). Always on by default (middleware_default=True).

    Config options:
        debug: Show detailed error messages and tracebacks. Default: False
    """

    middleware_name = "errors"
    middleware_order = 100
    middleware_default = True

    __slots__ = ("debug",)

    def __init__(
        self,
        app: ASGIApp,
        debug: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(app, **kwargs)
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - catch errors and return error response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Redirect as e:
            await self._send_redirect(send, e)
        except HTTPException as e:
            await self._send_http_error(send, e)
        except Exception as e:
            await self._send_server_error(send, e)

    async def _send_redirect(self, send: Send, exc: Redirect) -> None:
        """Send redirect response."""
        await send(
            {
                "type": "http.response.start",
                "status": exc.status_code,
                "headers": [(b"location", exc.url.encode())],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    async def _send_http_error(self, send: Send, exc: HTTPException) -> None:
        """Send HTTP error response from HTTPException."""
        body = exc.detail or ""
        body_bytes = body.encode("utf-8")

        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body_bytes)).encode()),
        ]
        if exc.headers:
            headers.extend((k.encode(), v.encode()) for k, v in exc.headers)

        await send(
            {"type": "http.response.start", "status": exc.status_code, "headers": headers}
        )
        await send({"type": "http.response.body", "body": body_bytes})

    async def _send_server_error(self, send: Send, error: Exception) -> None:
        """Send 500 error response for unhandled exceptions."""
        if self.debug:
            body = f"Internal Server Error\n\n{traceback.format_exc()}"
        else:
            body = "Internal Server Error"

        body_bytes = body.encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body_bytes)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body_bytes})


if __name__ == "__main__":
    pass
