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

"""Session tests (Macro 2 Phase 4): store contract suite + ASGI cookie flow.

The store contract suite is PARAMETRIZED over implementations (invariant
§5.9): today only ``MemorySessionStore``, but the core 1b file/db backends
plug into the SAME fixture. The cookie flow is driven directly through a
``SessionMixin/MiddlewareMixin/BaseServer`` composition at the ASGI level (no
uvicorn), the same driving style as ``test_middleware.py``.
"""

from __future__ import annotations

import time

import pytest

from genro_asgi_core import (
    Avatar,
    BaseApplication,
    BaseServer,
    MemorySessionStore,
    Session,
    SessionMixin,
    SessionStore,
)
from genro_asgi_core.middleware import MiddlewareMixin
from genro_asgi_core.types import Message, Receive, Scope, Send

# --- store contract suite (parametrized over implementations, §5.9) ---

STORE_IMPLEMENTATIONS = [MemorySessionStore]


@pytest.fixture(params=STORE_IMPLEMENTATIONS)
def store_cls(request):
    """Each session store implementation under contract test."""
    return request.param


class TestSessionStoreContract:
    def test_is_a_session_store(self, store_cls) -> None:
        assert isinstance(store_cls(), SessionStore)

    def test_create_default_is_anonymous(self, store_cls) -> None:
        assert store_cls().create().avatar is None

    def test_create_get_roundtrip(self, store_cls) -> None:
        store = store_cls()
        created = store.create(avatar=Avatar("alice"))
        fetched = store.get(created.id)
        assert fetched is created
        assert fetched.avatar.identity == "alice"

    def test_get_unknown_returns_none(self, store_cls) -> None:
        assert store_cls().get("nope") is None

    def test_ttl_expiry(self, store_cls) -> None:
        store = store_cls(default_ttl=3600)
        session = store.create()
        session.meta["last_access"] = time.time() - 10_000
        assert store.get(session.id) is None

    def test_delete(self, store_cls) -> None:
        store = store_cls()
        session = store.create()
        store.delete(session.id)
        assert store.get(session.id) is None

    def test_dump_restore_keeps_avatar_drops_data(self, store_cls) -> None:
        store = store_cls()
        session = store.create(avatar=Avatar("bob", ["user"]))
        session.data["k"] = "v"
        dumped = store.dump()
        fresh = store_cls()
        fresh.restore(dumped)
        restored = fresh.get(session.id)
        assert restored is not None
        assert restored.avatar.identity == "bob"
        assert restored.avatar.tags == ["user"]
        assert len(restored.data) == 0


# --- Session / Avatar units ---


class TestSessionUnit:
    def test_session_holds_avatar_and_bag(self) -> None:
        session = Session("tok", avatar=Avatar("alice"), ttl=3600)
        assert session.id == "tok"
        assert isinstance(session.avatar, Avatar)
        assert session.avatar.identity == "alice"
        assert not session.is_expired()

    def test_anonymous_session_avatar_is_none(self) -> None:
        assert Session("tok", avatar=None, ttl=3600).avatar is None

    def test_avatar_normalizes_none_tags(self) -> None:
        assert Avatar("alice", None).tags == []

    def test_touch_updates_last_access(self) -> None:
        session = Session("tok", avatar=None, ttl=3600)
        session.meta["last_access"] = 0.0
        session.touch()
        assert session.meta["last_access"] > 0.0

    def test_zero_ttl_is_expired(self) -> None:
        assert Session("tok", avatar=None, ttl=0).is_expired()


# --- ASGI cookie flow ---


class SessionServer(SessionMixin, MiddlewareMixin, BaseServer):
    """The Phase 4 composition: sessions armed over the middleware chain."""


class EchoApp(BaseApplication):
    """Echoes the id of the session attached to the scope, or a marker."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        session = scope.get("session")
        body = session.id.encode() if session is not None else b"no-session"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})


async def http_get(
    server: BaseServer, path: str = "/", cookie: str | None = None
) -> tuple[Scope, list[Message]]:
    """Drive one GET through ``server`` at the ASGI level; return the scope and what it sent."""
    headers = [(b"cookie", cookie.encode())] if cookie is not None else []
    scope: Scope = {"type": "http", "method": "GET", "path": path, "headers": headers}
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    await server(scope, receive, send)
    return scope, sent


def set_cookie_value(sent: list[Message]) -> str | None:
    start = next(m for m in sent if m["type"] == "http.response.start")
    for name, value in start["headers"]:
        if name == b"set-cookie":
            return value.decode()
    return None


def response_body(sent: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def cookie_token(sent: list[Message]) -> str:
    cookie = set_cookie_value(sent)
    assert cookie is not None
    return cookie.split(";")[0].split("=", 1)[1]


class TestSessionCookieFlow:
    async def test_first_request_sets_cookie(self) -> None:
        server = SessionServer(primary=EchoApp())
        scope, sent = await http_get(server)
        cookie = set_cookie_value(sent)
        assert cookie is not None
        assert cookie.startswith("session_id=")
        assert "HttpOnly" in cookie
        assert response_body(sent) == scope["session"].id.encode()

    async def test_returning_cookie_reuses_the_session(self) -> None:
        server = SessionServer(primary=EchoApp())
        _, first = await http_get(server)
        token = cookie_token(first)
        scope2, second = await http_get(server, cookie=f"session_id={token}")
        assert scope2["session"].id == token
        assert set_cookie_value(second) is None
        assert server.session(scope2) is scope2["session"]

    async def test_expired_cookie_issues_new_session(self) -> None:
        server = SessionServer(primary=EchoApp())
        _, first = await http_get(server)
        token = cookie_token(first)
        stored = server.session_store.get(token)
        assert stored is not None
        stored.meta["last_access"] = time.time() - 10_000
        scope2, second = await http_get(server, cookie=f"session_id={token}")
        assert scope2["session"].id != token
        assert set_cookie_value(second) is not None

    async def test_composition_without_session_mixin_returns_none(self) -> None:
        class Plain(MiddlewareMixin, BaseServer):
            pass

        server = Plain(primary=EchoApp())
        scope, sent = await http_get(server)
        assert server.session(scope) is None
        assert response_body(sent) == b"no-session"
        assert set_cookie_value(sent) is None

    async def test_explicit_session_false_disarms_the_middleware(self) -> None:
        server = SessionServer(primary=EchoApp(), middleware={"session": False})
        scope, sent = await http_get(server)
        assert scope.get("session") is None
        assert set_cookie_value(sent) is None
