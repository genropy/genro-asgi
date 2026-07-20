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

"""Standard middlewares tests (Macro 2 Phase 3): wellknown, logging, cors.

Same ASGI-level driving style as ``tests/test_middleware.py`` (no uvicorn):
a canned http scope, a recording ``send``, chain assembled through
``MiddlewareMixin`` composed over ``BaseServer``.
"""

from __future__ import annotations

import logging

from genro_asgi_core import BaseApplication, BaseServer, MiddlewareMixin
from genro_asgi_core.types import Message, Receive, Scope, Send


class MwServer(MiddlewareMixin, BaseServer):
    """Phase 2 composition: middleware capability over the base server."""


class RoutedApp(BaseApplication):
    """Test app: a plain 200 for every path it is given."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": f"ok:{scope['path']}".encode()})


async def http_request(
    server: BaseServer,
    path: str,
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> list[Message]:
    """Drive one request through ``server`` at the ASGI level; return what it sent."""
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    await server(scope, receive, send)
    return sent


def response_status(sent: list[Message]) -> int:
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def response_headers(sent: list[Message]) -> dict[bytes, bytes]:
    start = next(m for m in sent if m["type"] == "http.response.start")
    return dict(start["headers"])


def response_body(sent: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


class TestWellKnownMiddleware:
    async def test_probe_path_returns_404(self) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"wellknown": True})
        sent = await http_request(server, "/.well-known/probe")
        assert response_status(sent) == 404

    async def test_ordinary_path_still_reaches_the_app(self) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"wellknown": True})
        sent = await http_request(server, "/")
        assert response_status(sent) == 200
        assert response_body(sent) == b"ok:/"


class TestCORSMiddleware:
    async def test_preflight_returns_cors_headers(self) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"cors": True})
        sent = await http_request(
            server, "/", method="OPTIONS", headers=[(b"origin", b"https://example.test")]
        )
        assert response_status(sent) in (200, 204)
        headers = response_headers(sent)
        assert headers[b"access-control-allow-origin"] == b"*"
        assert b"access-control-allow-methods" in headers

    async def test_simple_get_carries_allow_origin_header(self) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"cors": True})
        sent = await http_request(server, "/", headers=[(b"origin", b"https://example.test")])
        assert response_status(sent) == 200
        assert response_headers(sent)[b"access-control-allow-origin"] == b"*"

    async def test_credentialed_wildcard_echoes_origin_with_vary(self) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"cors": {"allow_credentials": True}})
        sent = await http_request(server, "/", headers=[(b"origin", b"https://example.test")])
        headers = response_headers(sent)
        assert headers[b"access-control-allow-origin"] == b"https://example.test"
        assert headers[b"vary"] == b"Origin"
        assert headers[b"access-control-allow-credentials"] == b"true"


class TestLoggingMiddleware:
    async def test_records_one_entry_per_request(self) -> None:
        records: list[str] = []

        class RecordingHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record.getMessage())

        server = MwServer(primary=RoutedApp(), middleware={"logging": True})
        access_logger = logging.getLogger("genro_asgi_core.middleware.logging.LoggingMiddleware")
        handler = RecordingHandler()
        access_logger.addHandler(handler)
        access_logger.setLevel(logging.INFO)
        try:
            sent = await http_request(server, "/")
        finally:
            access_logger.removeHandler(handler)

        assert response_status(sent) == 200
        assert len(records) == 2
        assert records[0].startswith("<- GET /")
        assert records[1].startswith("-> GET / 200")


class TestDisabledByDefault:
    async def test_standard_middlewares_absent_without_switches(self) -> None:
        server = MwServer(primary=RoutedApp())

        wellknown_sent = await http_request(server, "/.well-known/probe")
        assert response_status(wellknown_sent) == 200

        cors_sent = await http_request(server, "/", headers=[(b"origin", b"https://example.test")])
        assert b"access-control-allow-origin" not in response_headers(cors_sent)

        records: list[str] = []

        class RecordingHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record.getMessage())

        access_logger = logging.getLogger("genro_asgi_core.middleware.logging.LoggingMiddleware")
        handler = RecordingHandler()
        access_logger.addHandler(handler)
        try:
            await http_request(server, "/")
        finally:
            access_logger.removeHandler(handler)
        assert records == []
