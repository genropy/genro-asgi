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

"""Request tests (Phase 1c/2): the HTTP request parses a real ASGI scope
(method/path/query/headers/cookies), body dispatch through ``handler_kwargs``
follows the content-type (form merges, hydrated body → ``body_data``, opaque
bytes → ``body_raw``, empty body → query only), the request id comes from the
header or is generated, TYTX mode is read off the header, and auth/session ride
the scope.

The ``db`` preparation layer is exercised end-to-end through the server: a fake
app touches ``request.db`` and the server drains ``closeConnection`` at end of
request; ``get_db`` never registers a cleanup; an unregistered code answers
``None``.
"""

from __future__ import annotations

import uuid
from typing import Any

from genro_asgi_core import Avatar, BaseApplication, BaseServer, Request, Response
from genro_asgi_core.types import Receive, Scope, Send


async def make_request(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    query: bytes = b"",
    body: bytes = b"",
    method: str = "GET",
    path: str = "/",
    scope_extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Request:
    """Build a ``Request`` from a synthetic ASGI scope and init it."""

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query,
        "headers": headers or [],
    }
    if scope_extra:
        scope.update(scope_extra)
    request = Request(scope, receive, **kwargs)
    await request.init()
    return request


class TestParsing:
    async def test_parses_method_path_query_headers_cookies(self) -> None:
        request = await make_request(
            method="post",
            path="/users",
            query=b"page=2&q=hello",
            headers=[
                (b"content-type", b"application/json"),
                (b"x-request-id", b"req-123"),
                (b"cookie", b"sid=abc; theme=dark"),
            ],
        )
        assert request.method == "POST"  # uppercased
        assert request.path == "/users"
        assert request.query == {"page": 2, "q": "hello"}  # typed via TYTX
        assert request.content_type == "application/json"
        assert request.cookies == {"sid": "abc", "theme": "dark"}
        assert request.id == "req-123"

    async def test_response_is_bound_back_to_the_request(self) -> None:
        request = await make_request()
        assert isinstance(request.response, Response)
        assert request.response.request is request

    async def test_numeric_id_headers_are_coerced_to_str(self) -> None:
        # asgi_data TYTX-hydrates header values: "123" arrives as int 123;
        # the id/external_id contract is str regardless.
        request = await make_request(
            headers=[(b"x-request-id", b"123"), (b"x-external-id", b"456")]
        )
        assert request.id == "123"
        assert request.external_id == "456"


class TestHandlerKwargs:
    async def test_json_body_passed_whole_as_body_data(self) -> None:
        request = await make_request(
            method="POST",
            query=b"page=1",
            headers=[(b"content-type", b"application/json")],
            body=b'{"name":"ada","age":36}',
        )
        assert request.data == {"name": "ada", "age": 36}
        assert request.handler_kwargs() == {"page": 1, "body_data": {"name": "ada", "age": 36}}

    async def test_urlencoded_body_merges_typed_and_wins_on_clash(self) -> None:
        request = await make_request(
            method="POST",
            query=b"a=9&page=2",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
            body=b"a=1&b=hello",
        )
        # asgi_data hydrates the urlencoded body via TYTX from_qs (genro-tytx
        # 0.10.0): the body arrives as a typed dict, not raw bytes.
        assert request.data == {"a": 1, "b": "hello"}
        kwargs = request.handler_kwargs()
        assert kwargs == {"a": 1, "b": "hello", "page": 2}  # body 'a' wins over query 'a'

    async def test_opaque_body_passed_as_body_raw(self) -> None:
        request = await make_request(
            method="POST",
            query=b"x=1",
            headers=[(b"content-type", b"application/octet-stream")],
            body=b"\x00\x01\x02",
        )
        assert request.data == b"\x00\x01\x02"
        assert request.handler_kwargs() == {"x": 1, "body_raw": b"\x00\x01\x02"}

    async def test_empty_body_yields_query_only(self) -> None:
        request = await make_request(method="GET", query=b"x=1&y=two")
        assert request.data is None
        assert request.handler_kwargs() == {"x": 1, "y": "two"}


class TestIdentityMetadata:
    async def test_request_id_generated_when_header_absent(self) -> None:
        request = await make_request()
        assert uuid.UUID(request.id)  # a valid uuid4, not empty

    async def test_external_id_from_header(self) -> None:
        request = await make_request(headers=[(b"x-external-id", b"corr-1")])
        assert request.external_id == "corr-1"

    async def test_tytx_mode_detected_from_header(self) -> None:
        request = await make_request(headers=[(b"x-tytx-transport", b"json")])
        assert request.tytx_mode is True
        assert request.tytx_transport == "json"

    async def test_no_tytx_header_means_plain_mode(self) -> None:
        request = await make_request()
        assert request.tytx_mode is False
        assert request.tytx_transport is None


class TestAuthSessionAccessors:
    async def test_auth_and_tags_from_scope(self) -> None:
        avatar = Avatar("alice", ["admin", "staff"])
        request = await make_request(scope_extra={"auth": avatar})
        assert request.auth is avatar
        assert request.auth_tags == ["admin", "staff"]

    async def test_anonymous_when_no_auth_on_scope(self) -> None:
        request = await make_request()
        assert request.auth is None
        assert request.auth_tags == []

    async def test_session_from_scope(self) -> None:
        session = object()
        request = await make_request(scope_extra={"session": session})
        assert request.session is session

    async def test_server_resolved_via_application(self) -> None:
        app = BaseApplication()
        server = BaseServer(primary=app)
        request = await make_request(application=app)
        assert request.application is app
        assert request.server is server


class FakeDb:
    """A stand-in db handler recording how often it is closed."""

    def __init__(self) -> None:
        self.closed = 0

    def closeConnection(self) -> None:
        self.closed += 1


class DbApp(BaseApplication):
    """Primary app that touches ``request.db`` (twice) and records the handler."""

    def __init__(self, **kwargs: Any) -> None:
        self.db_name: str | None = kwargs.pop("db_name", None)
        self.seen: dict[str, Any] = kwargs.pop("seen")
        super().__init__(**kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive, application=self)
        await request.init()
        self.seen["db"] = request.db
        self.seen["db_again"] = request.db  # second access is cached
        await request.response(scope, receive, send)


class GetDbApp(BaseApplication):
    """Primary app that resolves a db via ``get_db`` (no cleanup registration)."""

    def __init__(self, **kwargs: Any) -> None:
        self.seen: dict[str, Any] = kwargs.pop("seen")
        super().__init__(**kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive, application=self)
        await request.init()
        self.seen["db"] = request.get_db("default")
        await request.response(scope, receive, send)


async def drive(server: BaseServer, path: str = "/") -> None:
    """Drive one http request through the full server dispatch."""

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        pass

    await server(
        {"type": "http", "method": "GET", "path": path, "query_string": b"", "headers": []},
        receive,
        send,
    )


class TestDbPreparationLayer:
    async def test_db_returns_default_handler_and_closes_at_request_end(self) -> None:
        seen: dict[str, Any] = {}
        fake = FakeDb()
        server = BaseServer(primary=DbApp(seen=seen))
        server.add_database("default", fake)

        await drive(server)

        assert seen["db"] is fake
        assert seen["db_again"] is fake  # cached, same object
        assert fake.closed == 1  # cleanup registered once, drained by the server

    async def test_db_resolves_named_handler_from_app_db_name(self) -> None:
        seen: dict[str, Any] = {}
        fake = FakeDb()
        server = BaseServer(primary=DbApp(db_name="shop", seen=seen))
        server.add_database("shop", fake)

        await drive(server)

        assert seen["db"] is fake
        assert fake.closed == 1

    async def test_db_is_none_when_code_absent(self) -> None:
        seen: dict[str, Any] = {}
        server = BaseServer(primary=DbApp(seen=seen))  # no database registered

        await drive(server)

        assert seen["db"] is None

    async def test_get_db_does_not_register_cleanup(self) -> None:
        seen: dict[str, Any] = {}
        fake = FakeDb()
        server = BaseServer(primary=GetDbApp(seen=seen))
        server.add_database("default", fake)

        await drive(server)

        assert seen["db"] is fake
        assert fake.closed == 0  # get_db never queues closeConnection

    async def test_get_db_is_none_when_code_absent(self) -> None:
        seen: dict[str, Any] = {}
        server = BaseServer(primary=GetDbApp(seen=seen))  # nothing registered

        await drive(server)

        assert seen["db"] is None
