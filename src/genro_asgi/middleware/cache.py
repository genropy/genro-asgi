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
    """Cache middleware - adds caching headers to static file responses.

    Intercepts responses and adds ETag, Last-Modified, Cache-Control headers.
    Handles conditional requests (If-None-Match, If-Modified-Since) for 304 responses.

    Config options:
        max_age: Cache-Control max-age in seconds. Default: 3600 (1 hour)
        immutable: Add immutable directive for hashed filenames. Default: False
        public: Add public directive. Default: True
    """

    __slots__ = ("max_age", "immutable", "public")

    def __init__(
        self,
        app: ASGIApp,
        max_age: int = 3600,
        immutable: bool = False,
        public: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(app, **kwargs)
        self.max_age = max_age
        self.immutable = immutable
        self.public = public

    def _get_request_headers(self, scope: Scope) -> dict[str, str]:
        """Extract relevant cache headers from request."""
        headers: dict[str, str] = {}
        for name, value in scope.get("headers", []):
            name_str = name.decode("latin-1").lower()
            if name_str in ("if-none-match", "if-modified-since"):
                headers[name_str] = value.decode("latin-1")
        return headers

    def _compute_etag(self, path: Path) -> str:
        """Compute ETag from file mtime and size."""
        stat = path.stat()
        data = f"{stat.st_mtime}-{stat.st_size}".encode()
        return f'"{hashlib.md5(data).hexdigest()}"'

    def _format_http_date(self, timestamp: float) -> str:
        """Format timestamp as HTTP date."""
        return formatdate(timestamp, usegmt=True)

    def _check_not_modified(
        self,
        request_headers: dict[str, str],
        etag: str,
        mtime: float,
    ) -> bool:
        """Check if client cache is still valid."""
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
        """Build Cache-Control header value."""
        parts = []
        if self.public:
            parts.append("public")
        parts.append(f"max-age={self.max_age}")
        if self.immutable:
            parts.append("immutable")
        return ", ".join(parts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - handle cache headers."""
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
