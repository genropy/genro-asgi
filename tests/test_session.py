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

import pytest

from tests.storage_support import site_storage

from genro_asgi import (
    Avatar,
    BaseApplication,
    BaseServer,
    FileSessionStore,
    MemorySessionStore,
    Session,
    SessionMixin,
    SessionStore,
)
from genro_asgi.middleware import MiddlewareMixin
from genro_asgi.types import Message, Receive, Scope, Send

# --- store contract suite (parametrized over FACTORIES, §5.9) ---


def _memory_factory(tmp_path):
    """A factory building a fresh ``MemorySessionStore`` per call."""

    def make(**kwargs):
        return MemorySessionStore(**kwargs)

    return make


def _file_factory(tmp_path):
    """A factory building fresh ``FileSessionStore``s over one shared tmp mount."""

    def make(**kwargs):
        return FileSessionStore(site_storage(tmp_path), **kwargs)

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
        assert store_factory().create().avatar() is None

    def test_create_get_roundtrip(self, store_factory) -> None:
        store = store_factory()
        created = store.create(avatar=Avatar("alice"))
        fetched = store.get(created.id)
        assert fetched is created
        assert fetched.avatar().identity == "alice"

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
        assert restored.avatar().identity == "bob"
        assert restored.avatar().tags == ["user"]
        assert len(restored.data) == 0

    def test_save_is_in_the_contract(self, store_factory) -> None:
        # save() is part of the SessionStore Protocol on every backend; calling it
        # on a live session must succeed (the write-back seam).
        store = store_factory()
        session = store.create()
        session.attach_avatar(Avatar("carol", ["ops"]))
        store.save(session)
        again = store.get(session.id)
        assert again is not None
        assert again.avatar() is not None and again.avatar().identity == "carol"


# --- FileSessionStore specifics (D22 survival line) ---


class TestFileSessionStore:
    def test_session_survives_a_new_store_on_the_same_mount(self, tmp_path) -> None:
        store = FileSessionStore(site_storage(tmp_path))
        created = store.create(avatar=Avatar("carol", ["ops"]))
        fresh = FileSessionStore(site_storage(tmp_path))
        restored = fresh.get(created.id)
        assert restored is not None
        assert restored is not created
        assert restored.avatar().identity == "carol"
        assert restored.avatar().tags == ["ops"]
        assert len(restored.data) == 0

    def test_save_persists_an_attached_avatar_to_disk(self, tmp_path) -> None:
        store = FileSessionStore(site_storage(tmp_path))
        created = store.create()  # anonymous
        created.attach_avatar(Avatar("dave", ["admin"]))
        store.save(created)  # the write-back seam
        fresh = FileSessionStore(site_storage(tmp_path))
        restored = fresh.get(created.id)
        assert restored is not None
        assert restored.avatar() is not None and restored.avatar().identity == "dave"
        assert restored.avatar().tags == ["admin"]

    def test_corrupted_session_file_raises(self, tmp_path) -> None:
        storage = site_storage(tmp_path)
        store = FileSessionStore(storage)
        created = store.create()
        storage.node(f"site:sessions/{created.id}.json").write_text("not-json{{{")
        fresh = FileSessionStore(site_storage(tmp_path))
        with pytest.raises(json.JSONDecodeError):
            fresh.get(created.id)

    def test_delete_removes_the_file(self, tmp_path) -> None:
        storage = site_storage(tmp_path)
        store = FileSessionStore(storage)
        created = store.create()
        assert storage.node(f"site:sessions/{created.id}.json").exists()
        store.delete(created.id)
        assert not storage.node(f"site:sessions/{created.id}.json").exists()

    def test_get_with_traversal_session_id_raises(self, tmp_path) -> None:
        """A crafted cookie id may not read a file planted outside the prefix (Phase 10)."""
        storage = site_storage(tmp_path)
        store = FileSessionStore(storage)
        now = time.time()
        planted = {
            "meta": {"created_at": now, "last_access": now, "ttl": 3600},
            "avatars": {"root": {"identity": "intruder", "tags": ["SUPERADMIN"]}},
        }
        storage.node("site:secret.json").write_text(json.dumps(planted))
        with pytest.raises(ValueError, match="traversal"):
            store.get("../secret")

    def test_delete_with_traversal_session_id_raises(self, tmp_path) -> None:
        store = FileSessionStore(site_storage(tmp_path))
        with pytest.raises(ValueError, match="traversal"):
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
        assert isinstance(session.avatar(), Avatar)
        assert session.avatar().identity == "alice"
        assert not session.is_expired()

    def test_anonymous_session_avatar_is_none(self) -> None:
        assert Session("tok", avatar=None, ttl=3600).avatar() is None

    def test_avatar_normalizes_none_tags(self) -> None:
        assert Avatar("alice", None).tags == []

    def test_touch_updates_last_access(self) -> None:
        session = Session("tok", avatar=None, ttl=3600)
        session.meta["last_access"] = 0.0
        session.touch()
        assert session.meta["last_access"] > 0.0

    def test_zero_ttl_is_expired(self) -> None:
        assert Session("tok", avatar=None, ttl=0).is_expired()

    def test_new_session_is_not_dirty(self) -> None:
        assert Session("tok", avatar=None, ttl=3600).dirty is False

    def test_touch_does_not_mark_dirty(self) -> None:
        # a read-only request only touches last_access; it must stay non-dirty
        session = Session("tok", avatar=None, ttl=3600)
        session.touch()
        assert session.dirty is False

    def test_mark_dirty_and_clear(self) -> None:
        session = Session("tok", avatar=None, ttl=3600)
        session.mark_dirty()
        assert session.dirty is True
        session.clear_dirty()
        assert session.dirty is False

    def test_attach_avatar_marks_dirty(self) -> None:
        session = Session("tok", avatar=None, ttl=3600)
        session.attach_avatar(Avatar("alice"))
        assert session.dirty is True


# --- the dressing model: keyed avatars on one session ---


class TestSessionAvatars:
    def test_constructor_avatar_dresses_the_root_slot(self) -> None:
        session = Session("tok", avatar=Avatar("alice"), ttl=3600)
        assert session.avatar() is session.avatar(Session.ROOT_AVATAR_KEY)
        assert list(session.avatars) == ["root"]

    def test_attach_under_explicit_key_and_read_back(self) -> None:
        session = Session("tok", avatar=Avatar("alice"), ttl=3600)
        session.attach_avatar(Avatar("alice@erp", ["operator"]), "erp")
        assert session.avatar("erp").identity == "alice@erp"
        assert session.avatar().identity == "alice"  # root untouched by a sub-login

    def test_unclaimed_slot_is_none(self) -> None:
        session = Session("tok", avatar=Avatar("alice"), ttl=3600)
        assert session.avatar("erp") is None

    def test_keyed_attach_marks_dirty(self) -> None:
        session = Session("tok", avatar=Avatar("alice"), ttl=3600)
        session.clear_dirty()
        session.attach_avatar(Avatar("alice@erp"), "erp")
        assert session.dirty is True

    def test_avatars_view_is_enumerable(self) -> None:
        session = Session("tok", avatar=Avatar("alice"), ttl=3600)
        session.attach_avatar(Avatar("alice@erp"), "erp")
        assert sorted(session.avatars) == ["erp", "root"]
        assert len(session.avatars) == 2
        assert "erp" in session.avatars

    def test_avatars_view_is_read_only(self) -> None:
        session = Session("tok", avatar=Avatar("alice"), ttl=3600)
        with pytest.raises(TypeError):
            session.avatars["erp"] = Avatar("intruder")  # type: ignore[index]

    def test_memory_store_roundtrips_every_keyed_avatar(self) -> None:
        store = MemorySessionStore(default_ttl=3600)
        session = store.create(avatar=Avatar("alice", ["admin"]))
        session.attach_avatar(Avatar("alice@erp", ["operator"]), "erp")
        fresh = MemorySessionStore(default_ttl=3600)
        fresh.restore(store.dump())
        restored = fresh.get(session.id)
        assert restored.avatar().identity == "alice"
        assert restored.avatar().tags == ["admin"]
        assert restored.avatar("erp").identity == "alice@erp"
        assert restored.avatar("erp").tags == ["operator"]
        assert restored.dirty is False

    def test_file_store_roundtrips_every_keyed_avatar(self, tmp_path) -> None:
        storage = site_storage(tmp_path)
        session = FileSessionStore(storage).create(avatar=Avatar("alice", ["admin"]))
        session.attach_avatar(Avatar("alice@erp", ["operator"]), "erp")
        store = FileSessionStore(storage)
        store.save(session)
        restored = FileSessionStore(storage).get(session.id)
        assert restored.avatar().identity == "alice"
        assert restored.avatar("erp").identity == "alice@erp"
        assert restored.avatar("erp").tags == ["operator"]
        assert restored.dirty is False

    def test_anonymous_session_serializes_an_empty_wardrobe(self) -> None:
        store = MemorySessionStore(default_ttl=3600)
        session = store.create()
        assert store.dump()[session.id]["avatars"] == {}
        fresh = MemorySessionStore(default_ttl=3600)
        fresh.restore(store.dump())
        assert fresh.get(session.id).avatar() is None


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
        server = SessionServer(applications=[EchoApp(mount="")])
        scope, sent = await http_get(server)
        cookie = set_cookie_value(sent)
        assert cookie is not None
        assert cookie.startswith("session_id=")
        assert "HttpOnly" in cookie
        assert response_body(sent) == scope["session"].id.encode()

    async def test_returning_cookie_reuses_the_session(self) -> None:
        server = SessionServer(applications=[EchoApp(mount="")])
        _, first = await http_get(server)
        token = cookie_token(first)
        scope2, second = await http_get(server, cookie=f"session_id={token}")
        assert scope2["session"].id == token
        assert set_cookie_value(second) is None
        assert server.session(scope2) is scope2["session"]

    async def test_expired_cookie_issues_new_session(self) -> None:
        server = SessionServer(applications=[EchoApp(mount="")])
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

        server = Plain(applications=[EchoApp(mount="")])
        scope, sent = await http_get(server)
        assert server.session(scope) is None
        assert response_body(sent) == b"no-session"
        assert set_cookie_value(sent) is None

    async def test_explicit_session_false_disarms_the_middleware(self) -> None:
        server = SessionServer(applications=[EchoApp(mount="")], middleware={"session": False})
        scope, sent = await http_get(server)
        assert scope.get("session") is None
        assert set_cookie_value(sent) is None

    async def test_secure_option_adds_secure_cookie_attribute(self) -> None:
        server = SessionServer(applications=[EchoApp(mount="")], middleware={"session": {"secure": True}})
        _, sent = await http_get(server)
        cookie = set_cookie_value(sent)
        assert cookie is not None
        assert "Secure" in cookie

    async def test_default_cookie_has_no_secure_attribute(self) -> None:
        server = SessionServer(applications=[EchoApp(mount="")])
        _, sent = await http_get(server)
        cookie = set_cookie_value(sent)
        assert cookie is not None
        assert "Secure" not in cookie


# --- attach_avatar (login seam): identity attached in place, id unchanged ---


class TestAttachAvatar:
    def test_attach_sets_the_avatar_on_the_existing_session(self) -> None:
        session = MemorySessionStore().create()
        session.attach_avatar(Avatar("alice", ["admin"]))
        assert session.avatar() is not None
        assert session.avatar().identity == "alice"
        assert session.avatar().tags == ["admin"]

    def test_attach_preserves_session_data_and_id(self) -> None:
        store = MemorySessionStore()
        session = store.create()
        session_id = session.id
        session.data["cart"] = "kept"
        session.attach_avatar(Avatar("bob"))
        assert session.id == session_id  # the id never changes at login
        assert session.data["cart"] == "kept"  # the cart survives the login
        assert store.get(session_id) is session


# --- SessionMiddleware and login: the cookie is issued for a NEW session only ---


class PromotingApp(BaseApplication):
    """A login-like handler: attaches the avatar via the request facade in place."""

    def __init__(self, avatar: Avatar, **kwargs) -> None:
        super().__init__(**kwargs)
        self._avatar = avatar

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope["session"].attach_avatar(self._avatar)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": scope["session"].id.encode()})


class TestPromotedSessionCookie:
    async def test_promotion_in_a_first_request_rides_the_new_session_cookie(self) -> None:
        app = PromotingApp(Avatar("alice", ["admin"]), mount="")
        server = SessionServer(applications=[app])
        scope, sent = await http_get(server)
        session_id = scope["session"].id
        assert scope["session"].avatar() is not None
        assert scope["session"].avatar().identity == "alice"
        cookie = set_cookie_value(sent)  # issued for the NEW session, not for the login
        assert cookie is not None
        assert cookie.startswith(f"session_id={session_id}")
        assert "HttpOnly" in cookie
        assert response_body(sent) == session_id.encode()

    async def test_promotion_on_a_returning_session_sends_no_cookie(self) -> None:
        app = PromotingApp(Avatar("bob", ["user"]), mount="")
        server = SessionServer(applications=[app])
        anonymous = server.session_store.create()
        anonymous.data["cart"] = "kept"
        scope, sent = await http_get(server, cookie=f"session_id={anonymous.id}")
        assert scope["session"] is anonymous  # same session, same id
        assert scope["session"].avatar() is not None
        assert scope["session"].data["cart"] == "kept"  # the cart survives the login
        assert set_cookie_value(sent) is None  # the client's cookie is still valid

    async def test_unchanged_returning_session_still_sends_no_cookie(self) -> None:
        server = SessionServer(applications=[EchoApp(mount="")])
        _, first = await http_get(server)
        token = cookie_token(first)
        _, second = await http_get(server, cookie=f"session_id={token}")
        assert set_cookie_value(second) is None
