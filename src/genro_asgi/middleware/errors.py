# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Error Handling Middleware."""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class ErrorMiddleware(BaseMiddleware):
    """Error handling middleware - catches exceptions and returns error responses.

    Config options:
        debug: Show detailed error messages and tracebacks. Default: False
    """

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
        except Exception as e:
            await self._send_error_response(send, e)

    async def _send_error_response(self, send: Send, error: Exception) -> None:
        """Send error response."""
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
        await send(
            {
                "type": "http.response.body",
                "body": body_bytes,
            }
        )


if __name__ == "__main__":
    pass
