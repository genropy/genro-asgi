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

"""Shared ASGI-level test helpers, promoted from ``test_middleware_std.py``.

Every helper is a fixture returning a callable, so any test file can drive a
request through a composed server's ``__call__`` and read the recorded
messages without re-declaring the boilerplate: ``http_request`` runs one
request and returns the ``send`` messages; ``response_status`` /
``response_headers`` / ``response_body`` read that message list.
"""

from __future__ import annotations

from typing import Callable

import pytest

from genro_asgi_core.types import Message, Scope


@pytest.fixture
def http_request() -> Callable[..., object]:
    """Fixture: drive one request through a server at the ASGI level."""

    async def _http_request(
        server: object,
        path: str = "/",
        method: str = "GET",
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> list[Message]:
        scope: Scope = {"type": "http", "method": method, "path": path, "headers": headers or []}
        sent: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request"}

        async def send(message: Message) -> None:
            sent.append(message)

        await server(scope, receive, send)  # type: ignore[operator]
        return sent

    return _http_request


@pytest.fixture
def response_status() -> Callable[[list[Message]], int]:
    """Fixture: the status of the ``http.response.start`` message."""

    def _response_status(sent: list[Message]) -> int:
        return next(m["status"] for m in sent if m["type"] == "http.response.start")

    return _response_status


@pytest.fixture
def response_headers() -> Callable[[list[Message]], dict[bytes, bytes]]:
    """Fixture: the ``http.response.start`` headers as a byte-keyed dict."""

    def _response_headers(sent: list[Message]) -> dict[bytes, bytes]:
        start = next(m for m in sent if m["type"] == "http.response.start")
        return dict(start["headers"])

    return _response_headers


@pytest.fixture
def response_body() -> Callable[[list[Message]], bytes]:
    """Fixture: the concatenated ``http.response.body`` bytes."""

    def _response_body(sent: list[Message]) -> bytes:
        return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")

    return _response_body
