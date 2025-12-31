# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Compression middleware for ASGI applications.

Compresses HTTP responses using gzip when beneficial. Buffers the response
to determine if compression is worthwhile before sending.

Compression criteria:
    - Client accepts gzip (Accept-Encoding header contains "gzip")
    - Response size >= minimum_size
    - Content-Type is compressible (text/*, application/json, etc.)
    - Compressed size < original size

Config:
    minimum_size (int): Minimum bytes before compressing. Default: 500.
    compression_level (int): Gzip level 1-9. Default: 6.

Note:
    Adds Content-Encoding: gzip and Vary: Accept-Encoding headers.
    Updates Content-Length to compressed size.

Example:
    Enable in config.yaml::

        middleware:
          compression:
            minimum_size: 1000
            compression_level: 6
"""

from __future__ import annotations

import gzip
import io
from typing import TYPE_CHECKING, Any, MutableMapping

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class CompressionMiddleware(BaseMiddleware):
    """Gzip compression middleware for HTTP responses.

    Buffers responses and applies gzip compression when all criteria are met.
    Non-HTTP requests pass through unchanged.

    Attributes:
        minimum_size: Minimum response size in bytes to consider compression.
        compression_level: Gzip compression level (1=fast, 9=best).

    Class Attributes:
        middleware_name: "compression" - identifier for config.
        middleware_order: 900 - runs late to compress final response.
        middleware_default: False - disabled by default.
    """

    middleware_name = "compression"
    middleware_order = 900
    middleware_default = False

    __slots__ = ("minimum_size", "compression_level", "_compressible_types")

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        compression_level: int = 6,
        **kwargs: Any,
    ) -> None:
        """Initialize compression middleware.

        Args:
            app: Next ASGI application in the middleware chain.
            minimum_size: Minimum response size to compress. Defaults to 500.
            compression_level: Gzip level 1-9. Clamped to valid range. Defaults to 6.
            **kwargs: Additional arguments passed to BaseMiddleware.
        """
        super().__init__(app, **kwargs)
        self.minimum_size = minimum_size
        self.compression_level = min(9, max(1, compression_level))
        self._compressible_types = (
            b"text/",
            b"application/json",
            b"application/javascript",
            b"application/xml",
            b"application/xhtml+xml",
        )

    def _accepts_gzip(self, scope: Scope) -> bool:
        """Check if client accepts gzip encoding.

        Args:
            scope: ASGI scope with headers.

        Returns:
            True if Accept-Encoding header contains "gzip".
        """
        for name, value in scope.get("headers", []):
            if name == b"accept-encoding":
                return b"gzip" in value.lower()
        return False

    def _is_compressible(self, content_type: bytes | None) -> bool:
        """Check if content type should be compressed.

        Args:
            content_type: Content-Type header value or None.

        Returns:
            True if content type starts with a compressible prefix.

        Note:
            Compressible types: text/*, application/json, application/javascript,
            application/xml, application/xhtml+xml.
        """
        if not content_type:
            return False
        content_type = content_type.lower()
        return any(content_type.startswith(ct) for ct in self._compressible_types)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request with response compression.

        For HTTP requests where client accepts gzip, buffers the response
        and compresses if beneficial. Otherwise passes through unchanged.

        Args:
            scope: ASGI scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Note:
            Buffering is required to determine response size before deciding
            whether to compress. Streaming responses are fully buffered.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not self._accepts_gzip(scope):
            await self.app(scope, receive, send)
            return

        # Buffer response to check size and compress
        initial_message: MutableMapping[str, Any] | None = None
        body_parts: list[bytes] = []
        content_type: bytes | None = None

        async def send_buffered(message: MutableMapping[str, Any]) -> None:
            nonlocal initial_message, body_parts, content_type

            if message["type"] == "http.response.start":
                initial_message = message
                # Get content type
                for name, value in message.get("headers", []):
                    if name == b"content-type":
                        content_type = value
                        break

            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                more_body = message.get("more_body", False)

                if body:
                    body_parts.append(body)

                if not more_body:
                    # End of response - decide whether to compress
                    full_body = b"".join(body_parts)
                    await self._send_response(send, initial_message, full_body, content_type)

        await self.app(scope, receive, send_buffered)

    async def _send_response(
        self,
        send: Send,
        initial_message: MutableMapping[str, Any] | None,
        body: bytes,
        content_type: bytes | None,
    ) -> None:
        """Send buffered response, applying compression if beneficial.

        Args:
            send: ASGI send callable.
            initial_message: Buffered http.response.start message.
            body: Complete response body bytes.
            content_type: Content-Type header value or None.

        Note:
            Compression is skipped if:
            - Body size < minimum_size
            - Content-Type is not compressible
            - Compressed size >= original size
        """
        if initial_message is None:
            return

        should_compress = len(body) >= self.minimum_size and self._is_compressible(content_type)

        if should_compress:
            # Compress body
            buffer = io.BytesIO()
            with gzip.GzipFile(
                mode="wb", fileobj=buffer, compresslevel=self.compression_level
            ) as gz:
                gz.write(body)
            compressed_body = buffer.getvalue()

            # Only use compressed if smaller
            if len(compressed_body) < len(body):
                body = compressed_body
                # Update headers
                headers = [
                    (name, value)
                    for name, value in initial_message.get("headers", [])
                    if name not in (b"content-length", b"content-encoding")
                ]
                headers.append((b"content-encoding", b"gzip"))
                headers.append((b"content-length", str(len(body)).encode()))
                headers.append((b"vary", b"Accept-Encoding"))
                initial_message = {**initial_message, "headers": headers}

        await send(initial_message)
        await send({"type": "http.response.body", "body": body})


if __name__ == "__main__":
    pass
