# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Dispatcher - Routes requests to handlers via genro_routes Router."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from .response import JSONResponse

if TYPE_CHECKING:
    from .server import AsgiServer
    from .types import Receive, Scope, Send


class Dispatcher:
    """
    Routes ASGI requests to handlers via genro_routes Router.

    Converts URL paths to selectors, creates requests, invokes handlers,
    and converts results to responses. Used internally by AsgiServer.
    """

    __slots__ = ("server",)

    def __init__(self, server: AsgiServer) -> None:
        self.server = server

    @property
    def router(self) -> Any:
        """Proxy to server.router."""
        return self.server.router

    @property
    def request_registry(self) -> Any:
        """Proxy to server.request_registry."""
        return self.server.request_registry

    @property
    def logger(self) -> Any:
        """Proxy to server.logger."""
        return self.server.logger

    def path_to_selector(self, path: str) -> str:
        """
        Convert URL path to genro_routes selector.

        Examples:
            "/" -> "index"
            "/sites" -> "sites"
            "/_sys/sites" -> "_sys.sites"
            "/shop/products" -> "shop.products"
        """
        path = path.strip("/")
        if not path:
            return "index"
        return path.replace("/", ".")

    async def dispatch(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Dispatch request to handler via router.

        1. Convert path to selector
        2. Find handler in router
        3. Create and register request
        4. Call handler with appropriate params
        5. Convert result to response
        6. Cleanup request from registry
        """
        path = scope.get("path", "/")
        selector = self.path_to_selector(path)

        try:
            handler = self.router.get(selector)
        except (KeyError, NotImplementedError):
            response = JSONResponse(
                {"error": f"Not found: {path}"},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        request = await self.request_registry.create(scope, receive, send)

        # Set app_name from first path segment for metrics
        parts = path.strip("/").split("/")
        if parts and parts[0]:
            request.app_name = parts[0]

        try:
            kwargs = dict(request.query)

            sig = inspect.signature(handler)
            params = list(sig.parameters.keys())

            if params and params[0] in ("request", "req"):
                result = handler(request, **kwargs)
            else:
                result = handler(**kwargs)

            if inspect.isawaitable(result):
                result = await result

            response = request.make_response(result)
            await response(scope, receive, send)

        except Exception as e:
            self.logger.exception(f"Handler error: {e}")
            response = JSONResponse(
                {"error": str(e)},
                status_code=500,
            )
            await response(scope, receive, send)
        finally:
            self.request_registry.unregister(request.id)


if __name__ == "__main__":
    pass
