"""Compression Middleware.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

from typing import Callable, Any


class CompressionMiddleware:
    """Compression Middleware.

    Compresses response bodies using gzip when appropriate.
    """

    def __init__(
        self,
        app: Callable,
        minimum_size: int = 500,
        compression_level: int = 6
    ) -> None:
        """Initialize compression middleware.

        Args:
            app: ASGI application to wrap
            minimum_size: Minimum response size to compress (bytes)
            compression_level: Gzip compression level (1-9)
        """
        self.app = app
        self.minimum_size = minimum_size
        self.compression_level = compression_level

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable
    ) -> None:
        """ASGI interface.

        Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        # Stub implementation - just pass through to app
        await self.app(scope, receive, send)
