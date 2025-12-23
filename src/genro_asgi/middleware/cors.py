# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""CORS (Cross-Origin Resource Sharing) Middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, MutableMapping

from . import BaseMiddleware
from ..utils import normalize_list

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class CORSMiddleware(BaseMiddleware):
    """CORS middleware - adds Cross-Origin Resource Sharing headers.

    Handles preflight OPTIONS requests and adds CORS headers to responses.

    Config options:
        allow_origins: Origins allowed (list or comma-separated string). Default: ["*"]
        allow_methods: Methods allowed. Default: ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]
        allow_headers: Headers allowed. Default: ["*"]
        allow_credentials: Allow credentials. Default: False
        expose_headers: Headers to expose. Default: []
        max_age: Preflight cache time in seconds. Default: 600
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
        super().__init__(app, **kwargs)
        self.allow_origins = normalize_list(allow_origins, ["*"])
        self.allow_methods = normalize_list(
            allow_methods, ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"]
        )
        self.allow_headers = normalize_list(allow_headers, ["*"])
        self.allow_credentials = allow_credentials
        self.expose_headers = normalize_list(expose_headers)
        self.max_age = max_age

        self._allow_all_origins = "*" in self.allow_origins
        self._preflight_headers = self._build_preflight_headers()

    def _build_preflight_headers(self) -> list[tuple[bytes, bytes]]:
        """Build headers for preflight response."""
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
        """Get CORS headers for a response based on origin."""
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
        """ASGI interface - handle CORS."""
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
        """Handle preflight OPTIONS request."""
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
