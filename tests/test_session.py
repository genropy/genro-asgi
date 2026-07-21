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

"""Session tests (Macro 2 Phase 4 + core 1b Phase 3): store contract + cookie flow.

The store contract suite is PARAMETRIZED over FACTORIES (invariant §5.9):
callables returning a fresh configured store, so a backend needing a
storage/mount (``FileSessionStore``) plugs into the SAME suite as
``MemorySessionStore``. The cookie flow is driven directly through a
``SessionMixin/MiddlewareMixin/BaseServer`` composition at the ASGI level (no
uvicorn), the same driving style as ``test_middleware.py``.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from genro_asgi_core import (
    Avatar,
    BaseApplication,
    BaseServer,
    FileSessionStore,
    LocalStorage,
    MemorySessionStore,
    Session,
    SessionMixin,
    SessionStore,
)
from genro_asgi_core.middleware import MiddlewareMixin
from genro_asgi_core.types import Message, Receive, Scope, Send

# --- store contract suite (parametrized over FACTORIES, §5.9) ---


def _memory_factory(tmp_path):
    """A factory building a fresh ``MemorySessionStore`` per call."""

    def make(**kwargs):
        return MemorySessionStore(**kwargs)

    return make


def _file_factory(tmp_path):
    """A factory building fresh ``FileSessionStore``s over one shared tmp mount."""

    def make(**kwargs):
        return FileSessionStore(LocalStorage(base_dir=str(tmp_path)), **kwargs)

    return make


STORE_FACTORIES = [_memory_factory, _file_factory]


@pytest.fixture(params=STORE_FACTORIES)
def store_factory(request, tmp_path):
    """A callable returning a fresh configured store (memory or file-over-tmp)."""
    return request.param(tmp_path)


class TestSessionStoreContract:
    def test_is_a_session_store(self, store_factory) -> None:
        assert isinstance(store_factory(), SessionStore)

    def test_create_default_is_anonymous(self, store_factory) -> None:
        assert store_factory().create().avatar is None

    def test_create_get_roundtrip(self, store_factory) -> None:
        store = store_factory()
        created = store.create(avatar=Avatar("alice"))
        fetched = store.get(created.id)
        assert fetched is created
        assert fetched.avatar.identity == "alice"

    def test_get_unknown_returns_none(self, store_factory) -> None:
        assert store_factory().get("nope") is None

    def test_ttl_expiry(self, store_factory) -> None:
        store = store_factory(default_ttl=3600)
        session = store.create()
        session.meta["last_access"] = time.time() - 10_000
        assert store.get(session.id) is None

    def test_delete(self, store_factory) -> None:
        store = store_factory()
        session = store.create()
        store.delete(session.id)
        assert store.get(session.id) is None

    def test_purge_expired_removes_only_expired(self, store_factory) -> None:
        store = store_factory(default_ttl=3600)
        live = store.create()
        expired = store.create()
        expired.meta["last_access"] = time.time() - 10_000
        assert store.purge_expired() == 1
        assert store.get(live.id) is not None
        assert store.get(expired.id) is None

    def test_dump_restore_keeps_avatar_drops_data(self, store_factory) -> None:
        store = store_factory()
        session = store.create(avatar=Avatar("bob", ["user"]))
        session.data["k"] = "v"
        dumped = store.dump()
        fresh = store_factory()
        fresh.restore(dumped)
        restored = fresh.get(session.id)
        assert restored is not None
        assert restored.avatar.identity == "bob"
        assert restored.avatar.tags == ["user"]
        assert len(restored.data) == 0


# --- FileSessionStore specifics (D22 survival line) ---


class TestFileSessionStore:
    def test_session_survives_a_new_store_on_the_same_mount(self, tmp_path) -> None:
        store = FileSessionStore(LocalStorage(base_dir=str(tmp_path)))
        created = store.create(avatar=Avatar("carol", ["ops"]))
        fresh = FileSessionStore(LocalStorage(base_dir=str(tmp_path)))
        restored = fresh.get(created.id)
        assert restored is not None
        assert restored is not created
        assert restored.avatar.identity == "carol"
        assert restored.avatar.tags == ["ops"]
        assert len(restored.data) == 0

    def test_corrupted_session_file_raises(self, tmp_path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path))
        store = FileSessionStore(storage)
        created = store.create()
        storage.node(f"site:sessions/{created.id}.json").write_text("not-json{{{")
        fresh = FileSessionStore(LocalStorage(base_dir=str(tmp_path)))
        with pytest.raises(json.JSONDecodeError):
            fresh.get(created.id)

    def test_delete_removes_the_file(self, tmp_path) -> None:
        storage = LocalStorage(base_dir=str(tmp_path))
        store = FileSessionStore(storage)
        created = store.create()
        assert storage.node(f"site:sessions/{created.id}.json").exists
        store.delete(created.id)
        assert not storage.node(f"site:sessions/{created.id}.json").exists

    def test_get_with_traversal_session_id_raises(self, tmp_path) -> None:
        """A crafted cookie id may not read a file planted outside the prefix (Phase 10)."""
        storage = LocalStorage(base_dir=str(tmp_path))
        store = FileSessionStore(storage)
        now = time.time()
        planted = {
            "meta": {"created_at": now, "last_access": now, "ttl": 3600},
            "avatar": {"identity": "intruder", "tags": ["SUPERADMIN"]},
        }
        storage.node("site:secret.json").write_text(json.dumps(planted))
        with pytest.raises(ValueError, match="escapes mount 'site'"):
            store.get("../secret")

    def test_delete_with_traversal_session_id_raises(self, tmp_path) -> None:
        store = FileSessionStore(LocalStorage(base_dir=str(tmp_path)))
        with pytest.raises(ValueError, match="escapes mount 'site'"):
            store.delete("../secret")


# --- MemorySessionStore.restore drops an expired dumped session (Macro 2 item 8) ---


class TestMemoryStoreRestore:
    def test_restore_drops_expired_session(self) -> None:
        store = MemorySessionStore(default_ttl=3600)
        session = store.create(avatar=Avatar("bob"))
        dumped = store.dump()
        dumped[session.id]["meta"]["last_access"] = time.time() - 10_000
        fresh = MemorySessionStore()
        fresh.restore(dumped)
        assert fresh.get(session.id) is None


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

    async def test_secure_option_adds_secure_cookie_attribute(self) -> None:
        server = SessionServer(primary=EchoApp(), middleware={"session": {"secure": True}})
        _, sent = await http_get(server)
        cookie = set_cookie_value(sent)
        assert cookie is not None
        assert "Secure" in cookie

    async def test_default_cookie_has_no_secure_attribute(self) -> None:
        server = SessionServer(primary=EchoApp())
        _, sent = await http_get(server)
        cookie = set_cookie_value(sent)
        assert cookie is not None
        assert "Secure" not in cookie


# --- promote_session (login seam, option A) ---


class TestPromoteSession:
    def test_promote_replaces_anonymous_scope_session_with_identity(self) -> None:
        server = SessionServer(primary=EchoApp())
        anonymous = server.session_store.create()
        request = SimpleNamespace(scope={"session": anonymous})
        promoted = server.promote_session(request, Avatar("alice", ["admin"]))
        assert request.scope["session"] is promoted
        assert promoted is not anonymous
        assert promoted.avatar is not None
        assert promoted.avatar.identity == "alice"
        assert promoted.avatar.tags == ["admin"]

    def test_promoted_session_lives_in_the_store(self) -> None:
        server = SessionServer(primary=EchoApp())
        request = SimpleNamespace(scope={"session": server.session_store.create()})
        promoted = server.promote_session(request, Avatar("bob"))
        assert server.session_store.get(promoted.id) is promoted

    def test_promote_does_not_touch_cookies(self) -> None:
        server = SessionServer(primary=EchoApp())
        request = SimpleNamespace(scope={"session": server.session_store.create()})
        promoted = server.promote_session(request, Avatar("carol"))
        assert set(request.scope) == {"session"}
        assert isinstance(promoted, Session)


# --- SessionMiddleware emits Set-Cookie on a promoted/changed session (option A) ---


class PromotingApp(BaseApplication):
    """A login-like handler: swaps ``scope['session']`` for a fresh identity-bearing one."""

    def __init__(self, store: MemorySessionStore, avatar: Avatar, **kwargs) -> None:
        super().__init__(**kwargs)
        self._store = store
        self._avatar = avatar

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        promoted = self._store.create(avatar=self._avatar)
        scope["session"] = promoted
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": promoted.id.encode()})


class TestPromotedSessionCookie:
    async def test_promotion_in_a_first_request_sets_the_promoted_cookie(self) -> None:
        store = MemorySessionStore()
        app = PromotingApp(store, Avatar("alice", ["admin"]))
        server = SessionServer(primary=app, session_store=store)
        scope, sent = await http_get(server)
        promoted_id = scope["session"].id
        assert scope["session"].avatar is not None
        assert scope["session"].avatar.identity == "alice"
        cookie = set_cookie_value(sent)
        assert cookie is not None
        assert cookie.startswith(f"session_id={promoted_id}")
        assert "HttpOnly" in cookie
        assert response_body(sent) == promoted_id.encode()

    async def test_promotion_on_a_returning_session_reissues_the_cookie(self) -> None:
        store = MemorySessionStore()
        app = PromotingApp(store, Avatar("bob", ["user"]))
        server = SessionServer(primary=app, session_store=store)
        anonymous = store.create()
        scope, sent = await http_get(server, cookie=f"session_id={anonymous.id}")
        promoted_id = scope["session"].id
        assert promoted_id != anonymous.id
        assert cookie_token(sent) == promoted_id

    async def test_unchanged_returning_session_still_sends_no_cookie(self) -> None:
        server = SessionServer(primary=EchoApp())
        _, first = await http_get(server)
        token = cookie_token(first)
        _, second = await http_get(server, cookie=f"session_id={token}")
        assert set_cookie_value(second) is None
