# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""CORS (Cross-Origin Resource Sharing) middleware for ASGI applications.

Adds CORS headers to HTTP responses, enabling cross-origin requests from
browsers. Handles preflight OPTIONS requests automatically.

Config:
    allow_origins (list|str): Origins allowed. Default: ["*"]
    allow_methods (list|str): HTTP methods allowed. Default: common methods
    allow_headers (list|str): Request headers allowed. Default: ["*"]
    allow_credentials (bool): Allow credentials (cookies). Default: False
    expose_headers (list|str): Response headers to expose. Default: []
    max_age (int): Preflight cache time in seconds. Default: 600

Note:
    When allow_credentials is True, cannot use "*" for origins - the
    actual origin is echoed back instead.

Example:
    Enable CORS in config.yaml::

        middleware:
          cors:
            allow_origins: ["https://example.com", "https://app.example.com"]
            allow_credentials: true
            max_age: 3600
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, MutableMapping

from . import BaseMiddleware
from ..utils import split_and_strip

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class CORSMiddleware(BaseMiddleware):
    """CORS middleware for HTTP requests.

    Handles preflight OPTIONS requests and adds CORS headers to responses.
    Non-HTTP requests pass through unchanged.

    Attributes:
        allow_origins: List of allowed origins.
        allow_methods: List of allowed HTTP methods.
        allow_headers: List of allowed request headers.
        allow_credentials: Whether to allow credentials.
        expose_headers: List of headers to expose to browser.
        max_age: Preflight response cache time in seconds.

    Class Attributes:
        middleware_name: "cors" - identifier for config.
        middleware_order: 300 - runs after auth middleware.
        middleware_default: False - disabled by default.
    """

    middleware_name = "cors"
    middleware_order = 300
    middleware_default = False

    __slots__ = (
        "allow_origins",
        "allow_methods",
        "allow_headers",
        "allow_credentials",
        "expose_headers",
        "max_age",
        "_allow_all_origins",
        "_preflight_headers",
    )

    def __init__(
        self,
        app: ASGIApp,
        allow_origins: str | list[str] | None = None,
        allow_methods: str | list[str] | None = None,
        allow_headers: str | list[str] | None = None,
        allow_credentials: bool = False,
        expose_headers: str | list[str] | None = None,
        max_age: int = 600,
        **kwargs: Any,
    ) -> None:
        """Initialize CORS middleware.

        Args:
            app: Next ASGI application in the middleware chain.
            allow_origins: Origins to allow. Accepts list or comma-separated string.
                Use "*" to allow all origins. Defaults to ["*"].
            allow_methods: HTTP methods to allow. Defaults to common methods.
            allow_headers: Request headers to allow. Defaults to ["*"].
            allow_credentials: Allow cookies/auth headers. Defaults to False.
            expose_headers: Response headers to expose to browser. Defaults to [].
            max_age: Preflight cache time in seconds. Defaults to 600.
            **kwargs: Additional arguments passed to BaseMiddleware.
        """
        super().__init__(app, **kwargs)
        self.allow_origins = split_and_strip(allow_origins, ["*"])
        self.allow_methods = split_and_strip(
            allow_methods, ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"]
        )
        self.allow_headers = split_and_strip(allow_headers, ["*"])
        self.allow_credentials = allow_credentials
        self.expose_headers = split_and_strip(expose_headers)
        self.max_age = max_age

        self._allow_all_origins = "*" in self.allow_origins
        self._preflight_headers = self._build_preflight_headers()

    def _build_preflight_headers(self) -> list[tuple[bytes, bytes]]:
        """Build static headers for preflight OPTIONS response.

        Returns:
            List of ASGI header tuples for preflight response.

        Note:
            Called once during __init__ and cached in _preflight_headers.
            Includes: Access-Control-Allow-Methods, Max-Age, Allow-Headers,
            and Allow-Credentials if enabled.
        """
        headers = [
            (b"access-control-allow-methods", ", ".join(self.allow_methods).encode()),
            (b"access-control-max-age", str(self.max_age).encode()),
        ]

        if self.allow_headers:
            if "*" in self.allow_headers:
                headers.append((b"access-control-allow-headers", b"*"))
            else:
                headers.append(
                    (b"access-control-allow-headers", ", ".join(self.allow_headers).encode())
                )

        if self.allow_credentials:
            headers.append((b"access-control-allow-credentials", b"true"))

        return headers

    def _get_cors_headers(self, origin: str | None) -> list[tuple[bytes, bytes]]:
        """Get CORS headers for a response based on request origin.

        Args:
            origin: Origin header value from request, or None if not present.

        Returns:
            List of ASGI header tuples to add to response.
            Empty list if origin is not allowed or not present.

        Note:
            When allow_credentials is True and allow_all_origins is True,
            echoes the actual origin instead of "*" (per CORS spec).
        """
        headers: list[tuple[bytes, bytes]] = []

        if not origin:
            return headers

        # Check if origin is allowed
        if self._allow_all_origins:
            if self.allow_credentials:
                # Can't use * with credentials, must echo origin
                headers.append((b"access-control-allow-origin", origin.encode()))
            else:
                headers.append((b"access-control-allow-origin", b"*"))
        elif origin in self.allow_origins:
            headers.append((b"access-control-allow-origin", origin.encode()))
            headers.append((b"vary", b"Origin"))
        else:
            # Origin not allowed
            return []

        if self.allow_credentials:
            headers.append((b"access-control-allow-credentials", b"true"))

        if self.expose_headers:
            headers.append(
                (b"access-control-expose-headers", ", ".join(self.expose_headers).encode())
            )

        return headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request with CORS handling.

        For HTTP requests:
        - Preflight OPTIONS: Returns 200 with CORS headers
        - Other requests: Wraps send to add CORS headers to response

        Args:
            scope: ASGI scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Note:
            Non-HTTP requests pass through without CORS processing.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Get origin from request headers
        origin = None
        for name, value in scope.get("headers", []):
            if name == b"origin":
                origin = value.decode("latin-1")
                break

        method = scope.get("method", "GET")

        # Handle preflight OPTIONS request
        if method == "OPTIONS" and origin:
            await self._handle_preflight(scope, receive, send, origin)
            return

        # Wrap send to add CORS headers
        cors_headers = self._get_cors_headers(origin)

        async def send_with_cors(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start" and cors_headers:
                headers = list(message.get("headers", []))
                headers.extend(cors_headers)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cors)

    async def _handle_preflight(
        self, scope: Scope, receive: Receive, send: Send, origin: str
    ) -> None:
        """Handle preflight OPTIONS request.

        Args:
            scope: ASGI scope dictionary (unused but kept for consistency).
            receive: ASGI receive callable (unused).
            send: ASGI send callable for response.
            origin: Origin header value from request.

        Note:
            Returns 400 if origin is not allowed.
            Returns 200 with full CORS preflight headers if allowed.
        """
        headers = self._get_cors_headers(origin)
        if not headers:
            # Origin not allowed
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return

        headers.extend(self._preflight_headers)

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": b""})


if __name__ == "__main__":
    pass
