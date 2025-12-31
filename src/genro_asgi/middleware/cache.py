# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Cache Middleware - HTTP caching headers for static files.

Adds cache-related headers to responses:
- ETag: Based on file mtime + size for conditional requests
- Last-Modified: From file modification time
- Cache-Control: Configurable caching policy

Handles conditional requests:
- If-None-Match: Returns 304 if ETag matches
- If-Modified-Since: Returns 304 if file not modified

Config:
    max_age (int): Cache-Control max-age in seconds. Default: 3600 (1 hour).
    immutable (bool): Add immutable directive for hashed filenames. Default: False.
    public (bool): Add public directive. Default: True.

Note:
    Requires scope["_file_path"] to be set by the dispatcher for file responses.
    Only applies to GET/HEAD requests. Other methods pass through unchanged.

Example:
    Enable in config.yaml::

        middleware:
          cache:
            max_age: 86400
            immutable: true
            public: true
"""

from __future__ import annotations

import hashlib
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, MutableMapping

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send

__all__ = ["CacheMiddleware"]


class CacheMiddleware(BaseMiddleware):
    """Cache middleware for static file responses.

    Intercepts HTTP responses and adds caching headers (ETag, Last-Modified,
    Cache-Control). Handles conditional requests for 304 Not Modified responses.

    Attributes:
        max_age: Cache-Control max-age value in seconds.
        immutable: Whether to add immutable directive.
        public: Whether to add public directive.

    Class Attributes:
        middleware_name: "cache" - identifier for config.
        middleware_order: 900 - runs late to add headers to final response.
        middleware_default: False - disabled by default.
    """

    middleware_name = "cache"
    middleware_order = 900
    middleware_default = False

    __slots__ = ("max_age", "immutable", "public")

    def __init__(
        self,
        app: ASGIApp,
        max_age: int = 3600,
        immutable: bool = False,
        public: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize cache middleware.

        Args:
            app: Next ASGI application in the middleware chain.
            max_age: Cache-Control max-age in seconds. Defaults to 3600.
            immutable: Add immutable directive for versioned assets. Defaults to False.
            public: Add public directive allowing proxy caching. Defaults to True.
            **kwargs: Additional arguments passed to BaseMiddleware.
        """
        super().__init__(app, **kwargs)
        self.max_age = max_age
        self.immutable = immutable
        self.public = public

    def _get_request_headers(self, scope: Scope) -> dict[str, str]:
        """Extract conditional request headers.

        Args:
            scope: ASGI scope with headers.

        Returns:
            Dict with if-none-match and/or if-modified-since values.
        """
        headers: dict[str, str] = {}
        for name, value in scope.get("headers", []):
            name_str = name.decode("latin-1").lower()
            if name_str in ("if-none-match", "if-modified-since"):
                headers[name_str] = value.decode("latin-1")
        return headers

    def _compute_etag(self, path: Path) -> str:
        """Compute ETag from file mtime and size.

        Args:
            path: Path to the file.

        Returns:
            Quoted ETag string (e.g., '"abc123"').

        Note:
            Uses MD5 hash of mtime-size string. Fast but not cryptographic.
        """
        stat = path.stat()
        data = f"{stat.st_mtime}-{stat.st_size}".encode()
        return f'"{hashlib.md5(data).hexdigest()}"'

    def _format_http_date(self, timestamp: float) -> str:
        """Format timestamp as RFC 7231 HTTP date.

        Args:
            timestamp: Unix timestamp.

        Returns:
            HTTP date string (e.g., "Sun, 06 Nov 1994 08:49:37 GMT").
        """
        return formatdate(timestamp, usegmt=True)

    def _check_not_modified(
        self,
        request_headers: dict[str, str],
        etag: str,
        mtime: float,
    ) -> bool:
        """Check if client cache is still valid.

        Args:
            request_headers: Dict with conditional headers from request.
            etag: Current ETag of the resource.
            mtime: Current modification time of the resource.

        Returns:
            True if client cache is valid (304 should be returned).

        Note:
            Checks If-None-Match first (ETag), then If-Modified-Since.
            Supports multiple ETags in If-None-Match (comma-separated).
        """
        # Check If-None-Match (ETag)
        if_none_match = request_headers.get("if-none-match")
        if if_none_match:
            # Handle multiple ETags (comma-separated)
            client_etags = [e.strip() for e in if_none_match.split(",")]
            if etag in client_etags or "*" in client_etags:
                return True

        # Check If-Modified-Since
        if_modified_since = request_headers.get("if-modified-since")
        if if_modified_since:
            try:
                client_time = parsedate_to_datetime(if_modified_since).timestamp()
                # File not modified if mtime <= client's cached time
                if mtime <= client_time:
                    return True
            except (ValueError, TypeError):
                pass

        return False

    def _build_cache_control(self) -> str:
        """Build Cache-Control header value from configuration.

        Returns:
            Cache-Control directive string (e.g., "public, max-age=3600").
        """
        parts = []
        if self.public:
            parts.append("public")
        parts.append(f"max-age={self.max_age}")
        if self.immutable:
            parts.append("immutable")
        return ", ".join(parts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request with cache header handling.

        For HTTP GET/HEAD requests with file responses, adds caching headers
        and handles conditional requests (304 Not Modified).

        Args:
            scope: ASGI scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Note:
            Requires scope["_file_path"] to be set for file responses.
            Non-file responses pass through without cache headers.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Only apply to GET/HEAD requests
        method = scope.get("method", "GET")
        if method not in ("GET", "HEAD"):
            await self.app(scope, receive, send)
            return

        request_headers = self._get_request_headers(scope)
        file_path: Path | None = None
        response_started = False

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal file_path, response_started

            if message["type"] == "http.response.start":
                # Check if this looks like a file response by examining scope
                # The file path may be stored in scope by the dispatcher
                file_path = scope.get("_file_path")

                if file_path and file_path.exists():
                    stat = file_path.stat()
                    etag = self._compute_etag(file_path)
                    mtime = stat.st_mtime

                    # Check for 304 Not Modified
                    if self._check_not_modified(request_headers, etag, mtime):
                        # Send 304 response
                        await send(
                            {
                                "type": "http.response.start",
                                "status": 304,
                                "headers": [
                                    (b"etag", etag.encode("latin-1")),
                                    (
                                        b"cache-control",
                                        self._build_cache_control().encode("latin-1"),
                                    ),
                                ],
                            }
                        )
                        await send(
                            {
                                "type": "http.response.body",
                                "body": b"",
                            }
                        )
                        response_started = True
                        return

                    # Add cache headers to response
                    headers = list(message.get("headers", []))
                    headers.append((b"etag", etag.encode("latin-1")))
                    headers.append(
                        (b"last-modified", self._format_http_date(mtime).encode("latin-1"))
                    )
                    headers.append(
                        (b"cache-control", self._build_cache_control().encode("latin-1"))
                    )
                    message = {**message, "headers": headers}

                response_started = True
                await send(message)

            elif message["type"] == "http.response.body":
                if response_started:
                    await send(message)

        await self.app(scope, receive, send_wrapper)


if __name__ == "__main__":
    pass
