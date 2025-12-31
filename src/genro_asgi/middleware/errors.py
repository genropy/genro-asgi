# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Error handling middleware for ASGI applications.

Catches exceptions raised during request processing and converts them
to appropriate HTTP responses.

Exception handling:
    - Redirect: Returns 3xx redirect with Location header
    - HTTPException: Returns status code with detail message
    - Exception: Returns 500 Internal Server Error

Config:
    debug (bool): If True, include traceback in 500 responses. Default: False.

Note:
    This middleware is enabled by default (middleware_default=True) and
    runs early in the chain (middleware_order=100) to catch all errors.

Example:
    Middleware is auto-enabled, but can be configured::

        middleware:
          errors:
            debug: true  # Show tracebacks in development
"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

from . import BaseMiddleware
from ..exceptions import HTTPException, Redirect

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class ErrorMiddleware(BaseMiddleware):
    """Error handling middleware for HTTP requests.

    Wraps the application and catches exceptions, converting them to
    appropriate HTTP error responses. Non-HTTP requests pass through unchanged.

    Attributes:
        debug: If True, include stack traces in 500 error responses.

    Class Attributes:
        middleware_name: "errors" - identifier for config.
        middleware_order: 100 - runs early to catch all errors.
        middleware_default: True - enabled by default.
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
        """Initialize error middleware.

        Args:
            app: Next ASGI application in the middleware chain.
            debug: Show tracebacks in 500 responses. Defaults to False.
            **kwargs: Additional arguments passed to BaseMiddleware.
        """
        super().__init__(app, **kwargs)
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request with error handling.

        For HTTP requests, wraps the downstream app in try/except to catch
        and handle exceptions. Non-HTTP requests (WebSocket, lifespan) pass
        through without error handling.

        Args:
            scope: ASGI scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Note:
            Exception priority: Redirect > HTTPException > generic Exception
        """
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
        """Send HTTP redirect response.

        Args:
            send: ASGI send callable for response transmission.
            exc: Redirect exception with target URL and status code.

        Note:
            Uses exc.status_code (default 307) and sets Location header.
            Response body is empty.
        """
        await send(
            {
                "type": "http.response.start",
                "status": exc.status_code,
                "headers": [(b"location", exc.url.encode())],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    async def _send_http_error(self, send: Send, exc: HTTPException) -> None:
        """Send HTTP error response from HTTPException.

        Args:
            send: ASGI send callable for response transmission.
            exc: HTTPException with status_code, detail, and optional headers.

        Note:
            Content-Type: text/plain; charset=utf-8
            Body contains exc.detail message.
            Additional headers from exc.headers are appended.
        """
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
        """Send 500 Internal Server Error response.

        Args:
            send: ASGI send callable for response transmission.
            error: The unhandled exception that was caught.

        Note:
            If self.debug is True, includes full traceback in response body.
            Otherwise, returns generic "Internal Server Error" message.
            Content-Type: text/plain; charset=utf-8
        """
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
