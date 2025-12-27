# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Dispatcher - Routes requests to handlers via genro_routes Router."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from smartasync import smartasync

from .exceptions import (
    HTTPBadRequest,
    HTTPForbidden,
    HTTPNotFound,
    HTTPServiceUnavailable,
    HTTPUnauthorized,
)
from .request import set_current_request

if TYPE_CHECKING:
    from .server import AsgiServer
    from .types import Receive, Scope, Send

# Error mapping for router.node()
ROUTER_ERRORS: dict[str, type[Exception]] = {
    "not_found": HTTPNotFound,
    "not_authorized": HTTPForbidden,
    "not_authenticated": HTTPUnauthorized,
    "not_available": HTTPServiceUnavailable,
    "validation_error": HTTPBadRequest,
}


class Dispatcher:
    """Routes ASGI requests to handlers via genro_routes Router."""

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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - dispatch request to handler via router."""
        request = await self.request_registry.create(scope, receive, send)
        set_current_request(request)

        try:
            node = self.router.node(
                request.path,
                auth_tags=request.auth_tags,
                env_capabilities=request.env_capabilities,
                errors=ROUTER_ERRORS,
            )

            result = await smartasync(node)(**dict(request.query))

            request.response.set_result(result)
            await request.response(scope, receive, send)

        finally:
            set_current_request(None)
            self.request_registry.unregister(request.id)


if __name__ == "__main__":
    pass
