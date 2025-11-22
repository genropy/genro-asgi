"""Error Handling Middleware.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

from typing import Callable, Any


class ErrorMiddleware:
    """Error Handling Middleware.

    Catches exceptions and returns appropriate error responses.
    """

    def __init__(self, app: Callable, debug: bool = False) -> None:
        """Initialize error middleware.

        Args:
            app: ASGI application to wrap
            debug: Enable debug mode (show detailed error messages)
        """
        self.app = app
        self.debug = debug

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
