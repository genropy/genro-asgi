# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Logging Middleware - HTTP request/response access logging.

Logs incoming requests and outgoing responses with timing information.
Uses Python's standard logging module for output.

Log format:
    Request:  "<- GET /api/users from 192.168.1.1"
    Response: "-> GET /api/users 200 (12.5ms)"
    Error:    "-> GET /api/users ERROR: ... (12.5ms)"

Config:
    logger_name (str): Logger name. Default: "genro_asgi.access".
    level (str): Log level (DEBUG, INFO, WARNING, ERROR). Default: "INFO".
    include_headers (bool): Include request headers in DEBUG log. Default: False.
    include_query (bool): Include query string in request log. Default: True.

Example:
    Enable in config.yaml::

        middleware:
          logging:
            logger_name: "myapp.access"
            level: "DEBUG"
            include_headers: true
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, MutableMapping

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class LoggingMiddleware(BaseMiddleware):
    """Access logging middleware for HTTP requests.

    Logs request arrival and response completion with timing. Uses Python's
    logging module, allowing integration with existing logging configuration.

    Attributes:
        logger: Python Logger instance for access logs.
        level: Numeric log level (from logging module).
        include_headers: Whether to log request headers (at DEBUG level).
        include_query: Whether to include query string in request path.

    Class Attributes:
        middleware_name: "logging" - identifier for config.
        middleware_order: 200 - runs early to capture full request timing.
        middleware_default: False - disabled by default.
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
        """Initialize logging middleware.

        Args:
            app: Next ASGI application in the middleware chain.
            logger_name: Name for the Python logger. Defaults to "genro_asgi.access".
            level: Log level string (DEBUG, INFO, etc.). Defaults to "INFO".
            include_headers: Log headers at DEBUG level. Defaults to False.
            include_query: Include query string in path log. Defaults to True.
            **kwargs: Additional arguments passed to BaseMiddleware.
        """
        super().__init__(app, **kwargs)
        self.logger = logging.getLogger(logger_name)
        self.level = getattr(logging, level.upper(), logging.INFO)
        self.include_headers = include_headers
        self.include_query = include_query

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request with access logging.

        Logs request arrival, optionally headers, and response with timing.
        Exceptions are logged with ERROR level before re-raising.

        Args:
            scope: ASGI scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Note:
            Non-HTTP requests pass through without logging.
            Duration is measured in milliseconds using perf_counter.
        """
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
