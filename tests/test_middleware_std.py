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

"""Standard middlewares tests (Macro 2 Phase 3 + Macro 4 Phase 3 deferrals).

Same ASGI-level driving style as ``tests/test_middleware.py`` (no uvicorn):
a canned http scope, a recording ``send``, chain assembled through
``MiddlewareMixin`` composed over ``BaseServer``. The request-driving and
message-reading helpers now live in ``tests/conftest.py`` as fixtures
(``http_request``, ``response_status``, ``response_headers``, ``response_body``).

The Macro 4 Phase 3 additions cover the ``ErrorMiddleware`` on the real
``Response`` class (wire equivalence, forwarded exception headers, the
response-started guard) and the two previously-untested CORS branches
(restricted origins rejecting a foreign origin).
"""

from __future__ import annotations

import logging

import pytest

from genro_asgi_core import BaseApplication, BaseServer, MiddlewareMixin
from genro_asgi_core.exceptions import HTTPNotFound, HTTPUnauthorized, Redirect
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


class TestWellKnownMiddleware:
    async def test_probe_path_returns_404(self, http_request, response_status) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"wellknown": True})
        sent = await http_request(server, "/.well-known/probe")
        assert response_status(sent) == 404

    async def test_ordinary_path_still_reaches_the_app(
        self, http_request, response_status, response_body
    ) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"wellknown": True})
        sent = await http_request(server, "/")
        assert response_status(sent) == 200
        assert response_body(sent) == b"ok:/"


class TestCORSMiddleware:
    async def test_preflight_returns_cors_headers(
        self, http_request, response_status, response_headers
    ) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"cors": True})
        sent = await http_request(
            server, "/", method="OPTIONS", headers=[(b"origin", b"https://example.test")]
        )
        assert response_status(sent) in (200, 204)
        headers = response_headers(sent)
        assert headers[b"access-control-allow-origin"] == b"*"
        assert b"access-control-allow-methods" in headers

    async def test_simple_get_carries_allow_origin_header(
        self, http_request, response_status, response_headers
    ) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"cors": True})
        sent = await http_request(server, "/", headers=[(b"origin", b"https://example.test")])
        assert response_status(sent) == 200
        assert response_headers(sent)[b"access-control-allow-origin"] == b"*"

    async def test_credentialed_wildcard_echoes_origin_with_vary(
        self, http_request, response_headers
    ) -> None:
        server = MwServer(primary=RoutedApp(), middleware={"cors": {"allow_credentials": True}})
        sent = await http_request(server, "/", headers=[(b"origin", b"https://example.test")])
        headers = response_headers(sent)
        assert headers[b"access-control-allow-origin"] == b"https://example.test"
        assert headers[b"vary"] == b"Origin"
        assert headers[b"access-control-allow-credentials"] == b"true"

    async def test_restricted_origins_reject_a_foreign_origin(
        self, http_request, response_status, response_headers
    ) -> None:
        server = MwServer(
            primary=RoutedApp(), middleware={"cors": {"allow_origins": ["https://allowed.test"]}}
        )
        sent = await http_request(server, "/", headers=[(b"origin", b"https://foreign.test")])
        assert response_status(sent) == 200
        assert b"access-control-allow-origin" not in response_headers(sent)

    async def test_preflight_disallowed_origin_returns_400(
        self, http_request, response_status, response_headers
    ) -> None:
        server = MwServer(
            primary=RoutedApp(), middleware={"cors": {"allow_origins": ["https://allowed.test"]}}
        )
        sent = await http_request(
            server, "/", method="OPTIONS", headers=[(b"origin", b"https://foreign.test")]
        )
        assert response_status(sent) == 400
        assert b"access-control-allow-origin" not in response_headers(sent)


class RaisingApp(BaseApplication):
    """Test app raising the control-flow exceptions the errors middleware maps."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope["path"]
        if path == "/missing":
            raise HTTPNotFound("nothing here")
        if path == "/old":
            raise Redirect("/new")
        if path == "/challenge":
            raise HTTPUnauthorized("no", headers=[(b"www-authenticate", b"Bearer")])
        raise RuntimeError("boom")


class StartThenRaiseApp(BaseApplication):
    """Test app that starts the response, then raises — nothing more can be sent."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("boom after start")


class TestErrorMiddlewareOnResponse:
    async def test_http_exception_wire_shape(
        self, http_request, response_status, response_headers, response_body
    ) -> None:
        server = MwServer(primary=RaisingApp())
        sent = await http_request(server, "/missing")
        assert response_status(sent) == 404
        assert response_headers(sent)[b"content-type"] == b"text/plain; charset=utf-8"
        assert response_body(sent) == b"nothing here"

    async def test_plain_exception_maps_to_500(
        self, http_request, response_status, response_body
    ) -> None:
        server = MwServer(primary=RaisingApp())
        sent = await http_request(server, "/boom")
        assert response_status(sent) == 500
        assert response_body(sent) == b"Internal Server Error"

    async def test_redirect_sets_location_header(
        self, http_request, response_status, response_headers
    ) -> None:
        server = MwServer(primary=RaisingApp())
        sent = await http_request(server, "/old")
        assert response_status(sent) == 302
        assert response_headers(sent)[b"location"] == b"/new"

    async def test_exception_headers_are_forwarded(
        self, http_request, response_status, response_headers
    ) -> None:
        server = MwServer(primary=RaisingApp())
        sent = await http_request(server, "/challenge")
        assert response_status(sent) == 401
        assert response_headers(sent)[b"www-authenticate"] == b"Bearer"

    async def test_error_after_start_is_reraised_not_double_sent(self) -> None:
        server = MwServer(primary=StartThenRaiseApp())
        scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        sent: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request"}

        async def send(message: Message) -> None:
            sent.append(message)

        with pytest.raises(RuntimeError, match="after start"):
            await server(scope, receive, send)

        starts = [m for m in sent if m["type"] == "http.response.start"]
        assert len(starts) == 1
        assert starts[0]["status"] == 200


class TestLoggingMiddleware:
    async def test_records_one_entry_per_request(self, http_request, response_status) -> None:
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
    async def test_standard_middlewares_absent_without_switches(
        self, http_request, response_status, response_headers
    ) -> None:
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
