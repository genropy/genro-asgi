"""ASGI Application core.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

from typing import Callable, Any


class Application:
    """Minimal ASGI application.

    Provides the core ASGI interface and basic routing capabilities.
    """

    def __init__(self) -> None:
        """Initialize the ASGI application."""
        self.routes: dict[str, Callable] = {}
        self.middleware: list[Callable] = []

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
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
        elif scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)

    async def _handle_http(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable
    ) -> None:
        """Handle HTTP requests.

        Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        # Stub implementation
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"Genro ASGI - Minimal ASGI Foundation",
        })

    async def _handle_websocket(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable
    ) -> None:
        """Handle WebSocket connections.

        Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        # Stub implementation
        pass

    async def _handle_lifespan(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable
    ) -> None:
        """Handle lifespan events.

        Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        # Stub implementation
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
