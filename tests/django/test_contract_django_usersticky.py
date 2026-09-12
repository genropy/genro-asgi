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

"""Contract: the pool learns who Django logged in, and who logged out.

The request cycle here is the real one — Django's WSGI handler, its session
middleware, its authentication middleware, ``django.contrib.auth.login`` and
``logout`` on the real example project — served by a real ``DjangoWorker``
whose only double is the wire above it and the front in front of it, which a
test stands in for by packing the CALL itself. Nothing of the core is stubbed:
the login's tail runs, so a login ends with the connection in the deposit under
its new owner, and the request after it arrives the way the front sends it —
identity known, user frozen — and adopts him back.

What is held:

- a login announces ``connection_user_changed``, named by the session key the
  login cycled to, and that key is the one the front writes in its cookie;
- the connection reaches the deposit under the user, which is how the pool
  keeps sending him to this process;
- a logout takes the connection away, and the user with it;
- an anonymous visit stays a guest's and a refused login changes nobody;
- two browsers are two connections and two users;
- an environ with no worker in it — ``manage.py runserver`` — changes nothing.
"""

from __future__ import annotations

from typing import Any

import pytest

from genro_asgi_multiworker_spa.orchestration import FreezeHandler
from genro_asgi_multiworker_spa.orchestration.spa_worker import GUEST_PREFIX

from tests.django.test_contract_django_worker import (  # noqa: F401
    EXAMPLE_PATH,
    SETTINGS_MODULE,
    WORKER_NAME,
    django_engine,
    http_call,
    session_cookie,
)
from tests.spa.orchestration.conftest import attach_wire


@pytest.fixture
def deposit(tmp_path):
    """The real deposit the login's tail writes the connection to."""
    return FreezeHandler(tmp_path / "frozen_users")


@pytest.fixture
def worker(deposit, django_engine):  # noqa: F811
    """A forked worker's shape: the engine handed in, a stub wire, a slot."""
    from genro_asgi_django.worker import DjangoWorker

    worker = DjangoWorker(
        WORKER_NAME,
        freeze_handler=deposit,
        group_engine=django_engine,
        deposit_lock_retry_interval=0.01,
    )
    attach_wire(worker)
    yield worker
    worker.exit_process()


def login_call(username: str = "admin", password: str = "changeme") -> dict[str, Any]:
    """The CALL of a login, as the front packs an anonymous first request."""
    call = http_call(path="/login/")
    call["http"]["query_string"] = f"username={username}&password={password}"
    return call


def known_call(path: str, cookie: str, user: str) -> dict[str, Any]:
    """The CALL of a request the front knows the identity of, and sends frozen.

    What the front does after a login: the ``spa_connection_id`` cookie names a
    connection its indexes hold, so the CALL carries the identity, the
    connection and the flag that says the rows are in the deposit.
    """
    call = http_call(path=path, cookie=cookie)
    call["identity"] = user
    call["user_frozen"] = True
    call["http"]["cid"] = cookie.partition("=")[2]
    return call


async def serve(worker, call: dict[str, Any]) -> dict[str, Any]:
    """One request on a slot of its own, the way a live CALL is served."""
    worker.open_request_slot()
    return await worker._serve_request(call)


def events(worker, op: str) -> list[dict[str, Any]]:
    """The announcements of one kind, queued on the slot of the last request."""
    return [event for event in worker.worker_events if event["op"] == op]


class TestTheLoginIsToldToTheWorker:
    async def test_the_change_is_announced_on_the_cycled_session(self, worker) -> None:
        served = await serve(worker, login_call())
        assert served["body"] == b"logged in: admin\n"
        cid = session_cookie(served).partition("=")[2]
        announced = events(worker, "connection_user_changed")
        assert len(announced) == 1
        assert announced[0]["user"] == "admin"
        assert announced[0]["connection_id"] == cid
        assert announced[0]["previous_user"].startswith(GUEST_PREFIX)

    async def test_the_front_writes_the_cookie_of_the_login(self, worker) -> None:
        served = await serve(worker, login_call())
        assert served["connection_id"] == session_cookie(served).partition("=")[2]

    async def test_the_login_replaces_the_session_it_came_with(self, worker) -> None:
        anonymous = await serve(worker, http_call())
        first = session_cookie(anonymous)
        served = await serve(worker, login_call())
        assert session_cookie(served) != first

    async def test_the_connection_reaches_the_deposit_under_the_user(
        self, worker, deposit
    ) -> None:
        served = await serve(worker, login_call())
        cid = session_cookie(served).partition("=")[2]
        assert deposit.user_folders == {"admin"}
        assert deposit.get_item_header("admin", cid)["cause"] == "login"

    async def test_the_next_request_adopts_him_back(self, worker) -> None:
        logged_in = await serve(worker, login_call())
        cookie = session_cookie(logged_in)
        served = await serve(worker, known_call("/", cookie, "admin"))
        assert served["body"] == b"hello world\nuser: admin\nvisits: 1\n"
        assert worker.connection_register.get(cookie.partition("=")[2])["user"] == "admin"


class TestTheLogoutTakesTheConnectionAway:
    async def test_the_connection_and_the_user_leave(self, worker) -> None:
        logged_in = await serve(worker, login_call())
        cookie = session_cookie(logged_in)
        served = await serve(worker, known_call("/logout/", cookie, "admin"))
        assert served["body"] == b"logged out\n"
        assert list(worker.connection_register.keys()) == []
        assert "admin" not in worker.user_register

    async def test_the_departure_is_announced(self, worker) -> None:
        logged_in = await serve(worker, login_call())
        await serve(worker, known_call("/logout/", session_cookie(logged_in), "admin"))
        assert [event["user"] for event in events(worker, "drop_connection")] == ["admin"]
        assert [event["user"] for event in events(worker, "drop_user")] == ["admin"]


class TestEveryOtherRequestSaysNothing:
    async def test_an_anonymous_visit_stays_a_guest(self, worker) -> None:
        served = await serve(worker, http_call())
        cid = session_cookie(served).partition("=")[2]
        assert worker.connection_register.get(cid)["user"].startswith(GUEST_PREFIX)
        assert events(worker, "connection_user_changed") == []

    async def test_a_refused_login_changes_nobody(self, worker, deposit) -> None:
        served = await serve(worker, login_call(password="wrong"))
        assert served["status"] == 400
        assert events(worker, "connection_user_changed") == []
        assert deposit.user_folders == set()

    async def test_a_request_of_a_user_already_here_says_nothing(self, worker) -> None:
        logged_in = await serve(worker, login_call())
        await serve(worker, known_call("/", session_cookie(logged_in), "admin"))
        assert events(worker, "connection_user_changed") == []


class TestTwoBrowsersAreTwoConnections:
    async def test_each_one_has_its_own_connection_and_user(self, worker, deposit) -> None:
        first = await serve(worker, login_call())
        second = await serve(worker, login_call(username="mario"))
        assert session_cookie(first) != session_cookie(second)
        assert deposit.user_folders == {"admin", "mario"}
        assert (
            deposit.get_item_header("mario", session_cookie(second).partition("=")[2])
            is not None
        )


class TestTheMiddlewareWithoutThePool:
    def test_an_environ_with_no_worker_declares_nothing(self) -> None:
        # The same project under ``manage.py runserver``: the middleware runs,
        # finds no worker in the environ and does nothing at all.
        from genro_asgi_django.middleware import UserStickyMiddleware

        request = _StubRequest(session={"_auth_user_id": "1"}, session_key="k2")
        UserStickyMiddleware(lambda _: "response").declare_identity(request, None, "k1")

    def test_the_worker_is_in_the_environ_while_it_serves(self, worker) -> None:
        from genro_asgi_django.worker import WORKER_ENVIRON_KEY

        seen: list[Any] = []

        def watching_app(environ, start_response):
            seen.append(environ.get(WORKER_ENVIRON_KEY))
            start_response("200 OK", [])
            return [b""]

        worker.django_app = watching_app
        worker.serve_django({}, lambda status, headers, exc_info=None: None)
        assert seen == [worker]


class _StubRequest:
    """A request with a session and an environ, and nothing else."""

    def __init__(self, session: dict[str, Any], session_key: str) -> None:
        self.session = _StubSession(session, session_key)
        self.environ: dict[str, Any] = {}


class _StubSession(dict):
    """A session dict that also answers ``session_key``."""

    def __init__(self, values: dict[str, Any], session_key: str) -> None:
        super().__init__(values)
        self.session_key = session_key
