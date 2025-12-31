# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""AsgiContext - ASGI-specific routing context.

Provides access to request, response, and application resources for handlers
that need transport-specific functionality.

Note: Most handlers should NOT access context directly. They should receive
parameters from the dispatcher and return Python objects. Context access
is for special cases like setting cookies or accessing session data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from genro_routes import RoutingContext  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from .request import BaseRequest
    from .response import Response
    from .server import AsgiServer
    from .applications import AsgiApplication

__all__ = ["AsgiContext"]


class AsgiContext(RoutingContext):
    """ASGI-specific execution context.

    Provides access to HTTP request/response and application resources.
    Created per-request by the dispatcher and injected into RoutingClass.

    Attributes:
        request: Current HTTP request.
        response: Current HTTP response builder.
        app: Application instance handling the request.
        server: Server instance.
    """

    __slots__ = ("_request", "_app", "_server")

    def __init__(
        self,
        request: BaseRequest,
        app: AsgiApplication,
        server: AsgiServer,
    ) -> None:
        self._request = request
        self._app = app
        self._server = server

    @property
    def request(self) -> BaseRequest:
        """Current HTTP request."""
        return self._request

    @property
    def response(self) -> Response:
        """Current HTTP response builder."""
        return self._request.response

    @property
    def db(self) -> Any:
        """Database connection from request state or app."""
        # Try request state first, then app
        if hasattr(self._request, "state") and hasattr(self._request.state, "db"):
            return self._request.state.db
        if hasattr(self._app, "db"):
            return self._app.db
        return None

    @property
    def avatar(self) -> Any:
        """Current user identity (set by auth middleware)."""
        if hasattr(self._request, "avatar"):
            return self._request.avatar
        if hasattr(self._request, "state") and hasattr(self._request.state, "avatar"):
            return self._request.state.avatar
        return None

    @property
    def session(self) -> Any:
        """Session data (set by session middleware)."""
        if hasattr(self._request, "session"):
            return self._request.session
        if hasattr(self._request, "state") and hasattr(self._request.state, "session"):
            return self._request.state.session
        return None

    @property
    def app(self) -> AsgiApplication:
        """Application instance handling the request."""
        return self._app

    @property
    def server(self) -> AsgiServer:
        """Server instance."""
        return self._server


if __name__ == "__main__":
    pass
