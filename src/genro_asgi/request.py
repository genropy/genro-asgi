# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
        return str(self.scope.get("method", "GET"))

    @property
    def path(self) -> str:
        """Request path."""
        return str(self.scope.get("path", "/"))

    @property
    def query_string(self) -> bytes:
        """Query string (raw bytes)."""
        return bytes(self.scope.get("query_string", b""))

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
        return str(self.scope.get("scheme", "http"))

    @property
    def server(self) -> tuple[str, int]:
        """Server host and port."""
        server = self.scope.get("server")
        if server is None:
            return ("localhost", 8000)
        return (str(server[0]), int(server[1]))

    @property
    def client(self) -> tuple[str, int] | None:
        """Client host and port (if available)."""
        return self.scope.get("client")
