# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Logging Middleware - request/response logging."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, MutableMapping

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class LoggingMiddleware(BaseMiddleware):
    """Logging middleware - logs requests and responses.

    Config options:
        logger_name: Logger name. Default: "genro_asgi.access"
        level: Log level (DEBUG, INFO, WARNING, ERROR). Default: "INFO"
        include_headers: Include request headers in log. Default: False
        include_query: Include query string in log. Default: True
    """

    middleware_name = "logging"
    middleware_order = 200
    middleware_default = False

    __slots__ = ("logger", "level", "include_headers", "include_query")

    def __init__(
        self,
        app: ASGIApp,
        logger_name: str = "genro_asgi.access",
        level: str = "INFO",
        include_headers: bool = False,
        include_query: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(app, **kwargs)
        self.logger = logging.getLogger(logger_name)
        self.level = getattr(logging, level.upper(), logging.INFO)
        self.include_headers = include_headers
        self.include_query = include_query

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - log requests and responses."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        method = scope.get("method", "?")
        path = scope.get("path", "/")
        query = scope.get("query_string", b"").decode("utf-8")

        # Build request info
        request_info = f"{method} {path}"
        if self.include_query and query:
            request_info += f"?{query}"

        # Get client info
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        # Log request
        self.logger.log(self.level, f"<- {request_info} from {client_ip}")

        if self.include_headers:
            headers = {
                name.decode("latin-1"): value.decode("latin-1")
                for name, value in scope.get("headers", [])
            }
            self.logger.debug(f"   Headers: {headers}")

        # Track response status
        status_code: int = 0

        async def send_with_logging(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_with_logging)
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            self.logger.error(f"-> {request_info} ERROR: {e} ({duration:.1f}ms)")
            raise

        duration = (time.perf_counter() - start_time) * 1000
        self.logger.log(self.level, f"-> {request_info} {status_code} ({duration:.1f}ms)")


if __name__ == "__main__":
    pass
