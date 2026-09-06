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

"""A message of a page, from the browser to its worker and back (#68 phase 4).

Contract tests, entered where a real message enters: the socket. A message
becomes a synthetic request, the front packs it, the vertex places it, the
worker serves it on the row of the page it belongs to — and the answer comes
back with the id the browser correlates on.

``openchannel`` is what a page must send first, and it is the one command both
halves of the machine touch: the front validates the page against
``page_connection_map`` and writes the channel on its row through the worker;
the CONNECTION binds the page to its socket, and only because the front
answered 200 (owner, N30).

The pool here is real — a commander, a group, a worker on a UDS — through the
``worker_commander_lane`` fixture; the front is a real ``SpaApplication`` with
that commander in place.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from genro_asgi import BaseServer, MiddlewareMixin
from genro_asgi.applications.spa_app import SPA_CONNECTION_ID_COOKIE, SpaApplication
from genro_asgi.types import Message, Scope
from genro_asgi.wsx import WsxConnection, WsxEnvelope

PREFIX = "WSX://"
CID = "cid-a"
USER = "mario"
PAGE = "page-1"


class WsServer(MiddlewareMixin, BaseServer):
    """The composition a websocket needs."""


class XT_Front(SpaApplication):
    """The real front, with the pool of the fixture already in place."""

    def __init__(self, commander: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._commander = commander
        self.mount_channel_control()


class XT_Browser:
    """A browser that stays connected until the test lets it go."""

    def __init__(self) -> None:
        self.sent: list[Message] = []
        self._incoming: asyncio.Queue[Message] = asyncio.Queue()
        self._incoming.put_nowait({"type": "websocket.connect"})

    async def receive(self) -> Message:
        return await self._incoming.get()

    async def send(self, message: Message) -> None:
        self.sent.append(message)

    def says(self, envelope: WsxEnvelope) -> None:
        self._incoming.put_nowait({"type": "websocket.receive", "text": envelope.encode()})

    def leave(self) -> None:
        self._incoming.put_nowait({"type": "websocket.disconnect", "code": 1000})

    @property
    def answers(self) -> list[WsxEnvelope]:
        return [
            WsxEnvelope(m["text"])
            for m in self.sent
            if m["type"] == "websocket.send" and m.get("text", "").startswith(PREFIX)
        ]


class XT_Machine:
    """The whole machine of one story: server, front, pool, and one browser."""

    def __init__(self, lane: Any) -> None:
        self.lane = lane
        self.commander = lane.commander
        self.front = XT_Front(lane.commander, code="site0", mount="")
        self.server = WsServer(applications=[self.front])
        self.browser = XT_Browser()
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> XT_Machine:
        scope: Scope = {
            "type": "websocket",
            "path": "/_wsx",
            "headers": [
                (b"host", b"site.example"),
                (b"cookie", f"{SPA_CONNECTION_ID_COOKIE}={CID}".encode()),
            ],
            "subprotocols": [],
        }
        connection = WsxConnection(self.server, scope, self.browser.receive, self.browser.send)
        self._task = asyncio.create_task(connection.serve())
        await self.settle()
        return self

    async def __aexit__(self, *failure: Any) -> None:
        self.browser.leave()
        if self._task is not None:
            await self._task

    async def settle(self) -> None:
        """Let the connection's task, the lane and the worker move on."""
        for _ in range(20):
            await asyncio.sleep(0)

    async def message(self, envelope: WsxEnvelope) -> WsxEnvelope | None:
        """Say one message and hand back the answer, when it asked for one."""
        before = len(self.browser.answers)
        self.browser.says(envelope)
        for _ in range(40):
            await asyncio.sleep(0)
            if len(self.browser.answers) > before:
                return self.browser.answers[-1]
        return None

    async def open_channel(self, page_id: str = PAGE, **parameters: Any) -> WsxEnvelope | None:
        return await self.message(
            WsxEnvelope(
                id=f"open-{page_id}",
                method="WSK",
                path="/_wsx/openchannel",
                page_id=page_id,
                data={"parameters": parameters} if parameters else None,
            )
        )


@pytest.fixture
async def machine(worker_commander_lane):
    """The machine with one page already born on the worker, as a site does."""
    lane = worker_commander_lane
    lane.commander.connection_user_map[CID] = USER
    lane.commander.resolve_user(CID)
    await lane.verb("new_connection", CID, user=USER)
    await lane.verb("new_page", USER, PAGE, connection_id=CID)
    async with XT_Machine(lane) as running:
        yield running


class TestOpeningTheChannelOfAPage:
    async def test_the_page_is_told_its_channel_is_open(self, machine) -> None:
        answer = await machine.open_channel()
        assert answer is not None
        assert (answer.id, answer.status) == (f"open-{PAGE}", 200)

    async def test_the_worker_wrote_the_channel_on_the_row(self, machine) -> None:
        await machine.open_channel()
        assert machine.lane.worker.page_register.get(PAGE)["wsx"] is True

    async def test_the_parameters_the_page_asked_for_are_on_the_row(self, machine) -> None:
        await machine.open_channel(sequential=True)
        assert machine.lane.worker.page_register.get(PAGE)["wsx"] == {"sequential": True}

    async def test_the_page_now_speaks_on_this_socket(self, machine) -> None:
        assert machine.server.websockets.get_page_socket(PAGE) is None
        await machine.open_channel()
        assert machine.server.websockets.get_page_socket(PAGE) is not None

    async def test_saying_it_twice_changes_nothing(self, machine) -> None:
        await machine.open_channel()
        first = machine.server.websockets.get_page_socket(PAGE)
        answer = await machine.open_channel()
        assert answer.status == 200
        assert machine.server.websockets.get_page_socket(PAGE) is first


class TestAPageThatIsNotThisConnections:
    async def test_a_page_of_another_connection_is_refused(self, machine) -> None:
        machine.commander.page_connection_map["page-elsewhere"] = "cid-b"
        answer = await machine.open_channel("page-elsewhere")
        assert answer.status == 403

    async def test_a_page_nobody_ever_created_is_refused(self, machine) -> None:
        answer = await machine.open_channel("page-nowhere")
        assert answer.status == 403

    async def test_neither_is_ever_bound_to_the_socket(self, machine) -> None:
        machine.commander.page_connection_map["page-elsewhere"] = "cid-b"
        await machine.open_channel("page-elsewhere")
        await machine.open_channel("page-nowhere")
        assert machine.server.websockets.get_page_socket("page-elsewhere") is None
        assert machine.server.websockets.get_page_socket("page-nowhere") is None

    async def test_a_message_that_names_no_page_is_refused(self, machine) -> None:
        answer = await machine.message(
            WsxEnvelope(id="m1", method="WSK", path="/_wsx/openchannel")
        )
        assert answer.status == 400


class TestWhatTheWorkerRefuses:
    async def test_a_channel_for_a_page_the_worker_never_saw_is_an_error(
        self, machine
    ) -> None:
        # The vertex believes the page is this connection's — the front lets it
        # through — but the worker has no such row: the command fails there,
        # loudly, and nothing is bound.
        machine.commander.page_connection_map["ghost"] = CID
        answer = await machine.open_channel("ghost")
        assert answer.status == 500 and "never born here" in answer.data
        assert machine.server.websockets.get_page_socket("ghost") is None


class TestASocketWithNoCookie:
    async def test_a_message_from_a_connection_with_no_cookie_is_refused(
        self, worker_commander_lane
    ) -> None:
        # The SPA gates its handshake on the cookie, so this cannot happen
        # through the front door; the command refuses it anyway, because the
        # answer must never be "some connection".
        machine = XT_Machine(worker_commander_lane)
        scope: Scope = {
            "type": "websocket",
            "path": "/_wsx",
            "headers": [(b"host", b"site.example")],
            "subprotocols": [],
        }
        connection = WsxConnection(
            machine.server, scope, machine.browser.receive, machine.browser.send
        )
        task = asyncio.create_task(connection.serve())
        await machine.settle()
        answer = await machine.open_channel()
        assert answer.status == 400
        machine.browser.leave()
        await task


class TestTheServerSpeaksToTheOpenedPage:
    async def test_the_worker_reaches_the_browser_through_the_vertex(self, machine) -> None:
        # The whole road back: the site's own code calls `send_message` on a
        # pool thread, the CALL climbs the lane, the front finds the socket.
        await machine.open_channel()
        delivered = await machine.lane.verb("send_message", PAGE, "/main/refresh", {"n": 1})
        await machine.settle()
        assert delivered is True
        pushed = [m for m in machine.browser.answers if m.id is None]
        assert [(m.path, m.data, m.page_id) for m in pushed] == [
            ("/main/refresh", {"n": 1}, PAGE)
        ]

    async def test_a_page_that_never_opened_its_channel_is_reachable_by_nobody(
        self, machine
    ) -> None:
        delivered = await machine.lane.verb("send_message", PAGE, "/main/refresh")
        assert delivered is False

    async def test_a_page_the_vertex_no_longer_knows_is_reachable_by_nobody(
        self, machine
    ) -> None:
        # The fold dropped the page from the map: the socket may still hold a
        # stale binding, and the branch validates before it writes.
        await machine.open_channel()
        machine.commander.page_connection_map.pop(PAGE)
        delivered = await machine.lane.verb("send_message", PAGE, "/main/refresh")
        assert delivered is False
