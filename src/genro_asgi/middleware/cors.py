"""CORS Middleware.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

from typing import Callable, Any


class CORSMiddleware:
    """CORS (Cross-Origin Resource Sharing) Middleware.

    Adds appropriate CORS headers to responses.
    """

    def __init__(
        self,
        app: Callable,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None
    ) -> None:
        """Initialize CORS middleware.

        Args:
            app: ASGI application to wrap
            allow_origins: Allowed origins (default: ["*"])
            allow_methods: Allowed methods (default: ["*"])
            allow_headers: Allowed headers (default: ["*"])
        """
        self.app = app
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]

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
