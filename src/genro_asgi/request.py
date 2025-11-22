"""ASGI Request utilities.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

from typing import Any


class Request:
    """ASGI Request wrapper.

    Provides convenient access to ASGI scope information.
    """

    def __init__(self, scope: dict[str, Any]) -> None:
        """Initialize request from ASGI scope.

        Args:
            scope: ASGI connection scope
        """
        self.scope = scope

    @property
    def method(self) -> str:
        """HTTP method (GET, POST, etc.)."""
        return self.scope.get("method", "GET")

    @property
    def path(self) -> str:
        """Request path."""
        return self.scope.get("path", "/")

    @property
    def query_string(self) -> bytes:
        """Query string (raw bytes)."""
        return self.scope.get("query_string", b"")

    @property
    def headers(self) -> dict[str, str]:
        """Request headers (decoded)."""
        return {
            name.decode("latin1"): value.decode("latin1")
            for name, value in self.scope.get("headers", [])
        }

    @property
    def scheme(self) -> str:
        """URL scheme (http or https)."""
        return self.scope.get("scheme", "http")

    @property
    def server(self) -> tuple[str, int]:
        """Server host and port."""
        return self.scope.get("server", ("localhost", 8000))

    @property
    def client(self) -> tuple[str, int] | None:
        """Client host and port (if available)."""
        return self.scope.get("client")
