# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Compression Middleware - gzip response compression."""

from __future__ import annotations

import gzip
import io
from typing import TYPE_CHECKING, Any, MutableMapping

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class CompressionMiddleware(BaseMiddleware):
    """Compression middleware - compresses responses with gzip.

    Only compresses when:
    - Client accepts gzip (Accept-Encoding header)
    - Response is larger than minimum_size
    - Content-Type is compressible (text/*, application/json, etc.)

    Config options:
        minimum_size: Minimum response size to compress (bytes). Default: 500
        compression_level: Gzip level 1-9 (1=fast, 9=best). Default: 6
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
        """Check if client accepts gzip encoding."""
        for name, value in scope.get("headers", []):
            if name == b"accept-encoding":
                return b"gzip" in value.lower()
        return False

    def _is_compressible(self, content_type: bytes | None) -> bool:
        """Check if content type is compressible."""
        if not content_type:
            return False
        content_type = content_type.lower()
        return any(content_type.startswith(ct) for ct in self._compressible_types)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - handle compression."""
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
        """Send response, compressing if appropriate."""
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
