# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Dispatcher - Routes ASGI requests to handlers via genro-routes.

The Dispatcher is the innermost layer of the middleware chain. It:
1. Creates Request from ASGI scope via RequestRegistry
2. Resolves the handler via router.node() with auth filtering
3. Calls the handler with query parameters
4. Sets the result on Response via set_result()
5. Sends the ASGI response

Request flow:
    scope → RequestRegistry.create() → Request
         → router.node(path, auth_tags, env_capabilities, errors)
         → handler(**query)
         → response.set_result(result, metadata)
         → response(scope, receive, send)

Error mapping (ROUTER_ERRORS):
    Router errors are mapped to HTTP exceptions:
    - not_found → HTTPNotFound (404)
    - not_authorized → HTTPForbidden (403)
    - not_authenticated → HTTPUnauthorized (401)
    - not_available → HTTPServiceUnavailable (503)
    - validation_error → HTTPBadRequest (400)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from genro_routes import is_result_wrapper
from smartasync import smartasync

from ..exceptions import (
    HTTPBadRequest,
    HTTPForbidden,
    HTTPNotFound,
    HTTPServiceUnavailable,
    HTTPUnauthorized,
)
from ..request import set_current_request

if TYPE_CHECKING:
    from .server import AsgiServer
    from ..types import Receive, Scope, Send

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

            if is_result_wrapper(result):
                metadata = {**node.metadata, **result.metadata}
                request.response.set_result(result.value, metadata)
            else:
                request.response.set_result(result, node.metadata)
            await request.response(scope, receive, send)

        finally:
            set_current_request(None)
            self.request_registry.unregister()


if __name__ == "__main__":
    pass
