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

"""Macro 2 end to end: the worker is born, serves, parks a user, wakes him, leaves.

One story on the real things: a real child process running the package's own
``WorkerEntry``, a real Unix socket under the M1 ``WorkerHandler``, a real
deposit on disk read back from the parent side through a ``FreezeHandler`` of
its own. What is doubled is only what Macro 3 will bring: the group above the
handler (``GroupStub``) and the driver of the story, which plays the fold — it
is the test that says who is on board and that orders the departure.

The worker in the child is ``DrivenWorker``, a ``SpaWorker`` subclass of this
test package: it fills the ``wsgi_app`` seam with a tiny site, the way the
genropy-asgi bridge fills it with a whole one, and it answers three orders the
wire of Macro 2 does not carry — see its docstring, which declares those
routing keys as the test's own.

The story, in order: it is born with a photo and the global store on board; it
serves http calls through the seam, and the rows are born and the clocks
stamped; the driver orders the shot, and inside it the user who went silent is
flagged for cession by the VALVE — one more reason for a ``'T'``, not a road of
its own — while the one who has just spoken is kept; past the gate the silent
one is in the deposit with his placement to be assigned and his row is gone from
memory entirely; his next call carries the verdict and he comes home — to
whatever worker the vertex will name, which here is this one because there is
only one; the driver orders the departure and the reply to that order carries
the flagged photo; past the gate everybody is in the deposit and the process
ENDS BY ITSELF, exit code 0 and nobody killed it. That death is still denounced
WILD — in Macro 2 nothing marks it governed — and the successor launched on the
same name and socket presents itself with a fresh photo over a deposit nothing
has swept. That last picture is what Macro 3 inherits.

The sockets and the deposit live under a short ``mkdtemp`` root: the system caps
a UDS path at about a hundred characters and pytest's own directory is already
past it, which is the very reason worker names are short.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker, WorkerHandler
from genro_asgi.spa.orchestration.worker_connector import WORKER_SNAPSHOT_KEY

WORKER_NAME = "standard_0001"
GROUP = "standard"
ENTRY_MODULE = "genro_asgi.spa.orchestration.worker_entry"
DRIVEN_WORKER = f"{__name__}:DrivenWorker"

#: The three orders of this story. They are the TEST's own routing keys, not the
#: protocol's: Macro 2 routes the beat and the http form and nothing else, so
#: the shot, the transfer cycle and the departure — all verbs of the worker —
#: are reachable from the parent only through a subclass that answers for them.
#: The group of Macro 3 is what will send the real ones, and in the machine
#: proper the first two are not orders at all: the shot is taken by whoever
#: composes a due photo, and the cycle follows it.
PLAN_ORDER = "/op/plan_transfers"
EXECUTE_ORDER = "/op/execute_transfers"
QUIT_ORDER = "/op/quit"

#: The silence past which the valve parks a user, and the gate the departures
#: wait out — both shrunk from their own defaults through the spawn grammar, so
#: the story is told in fractions of a second instead of in seconds.
IDLE_DELAY = 0.5
GATE_DELAY = 0.5

#: The bounds every wait of this test is given: multiples of the times above and
#: of the handler's own beat timeout, never a measure of anything.
CALL_TIMEOUT = 10.0
DEATH_TIMEOUT = 15.0


class DrivenWorker(SpaWorker):
    """The worker of the story: it hosts a tiny site, and it takes three orders.

    The site is the real seam — ``wsgi_app``, what the genropy-asgi bridge
    assigns — and it answers with the facts of the request plus the global store
    this process was handed at its presentation, which is how the parent reads
    back what the child holds.

    The three orders are this test's own. ``plan_transfers``,
    ``execute_transfers`` and ``quit`` are verbs of ``SpaWorker``, but no op of
    Macro 2 routes to any of them: the beat and the http form are the whole of
    ``answer_call``. Rather than teach the protocol something the design has not
    decided, the subclass — the place a consumer already extends the worker —
    answers for them, exactly as the M1 child stub answers for the deposit
    orders it is driven with.
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.wsgi_app = self.tiny_site
        self.leaving: asyncio.Task[None] | None = None

    def tiny_site(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        """The WSGI callable: say back who asked, for what, and what this process holds."""
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/plain"),
                ("X-Worker", self.name),
                ("X-Global-Store", str(self.global_register_item_tytx)),
            ],
        )
        return [f"{environ['REQUEST_METHOD']} {environ['PATH_INFO']} "
                f"for {environ['genro.identity']}".encode()]

    async def answer_call(self, frame: Any) -> None:
        """Answer the three orders of the driver, and hand everything else upstairs.

        Args:
            frame: the CALL as it came off the wire.

        The shot is taken BEFORE the reply is composed, which is the whole point
        of the shot logic: the photo riding the reply is the one the transfers
        just flagged. The cycle order is answered when the cycle is OVER, so the
        reply carries what the departures said and the picture they left.
        """
        if frame.path == PLAN_ORDER:
            self.plan_transfers()
            await self.send_reply(frame, result={})
        elif frame.path == EXECUTE_ORDER:
            await self.execute_transfers()
            await self.send_reply(frame, result={})
        elif frame.path == QUIT_ORDER:
            self.leaving = asyncio.create_task(self.quit())
            await asyncio.sleep(0)
            await self.send_reply(frame, result={})
        else:
            await super().answer_call(frame)


class GroupStub:
    """The GroupHandler seen from below: what it is told, and who was on board when."""

    def __init__(self) -> None:
        self.aborted: list[Any] = []
        self.users_on_board: list[set[str]] = []

    def on_worker_abort(self, worker_handler: Any) -> None:
        self.aborted.append(worker_handler)
        self.users_on_board.append(set(worker_handler.hosted_users))


def http_call(cid: str, identity: str, *, path: str, **payload: Any) -> dict[str, Any]:
    """The http CALL form as the front packs it: the request, and who it is for."""
    return {
        "http": {
            "method": "GET",
            "path": path,
            "query_string": "",
            "headers": [["host", "site.example:8080"]],
            "body": "",
            "cid": cid,
        },
        "identity": identity,
        **payload,
    }


def body_of(reply: dict[str, Any]) -> str:
    """The site's answer, decoded out of the wire form."""
    return base64.b64decode(reply["result"]["body"]).decode()


def announced(reply: dict[str, Any]) -> list[str]:
    """The protocol names the reply carried up, in order."""
    return [event["op"] for event in reply["events"]]


async def wait_for(condition, timeout: float = CALL_TIMEOUT) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("the story never reached the awaited state")
        await asyncio.sleep(0.01)


@pytest.fixture
def group():
    return GroupStub()


@pytest.fixture
def story_root():
    """The short root holding both the socket directory and the deposit."""
    root = Path(tempfile.mkdtemp(prefix="gnrm2_"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def deposit(story_root):
    """The deposit as the parent reads it — the same root the child is given."""
    return FreezeHandler(story_root / "frozen_users")


@pytest.fixture
async def handler(story_root, group, monkeypatch):
    """The handler under test; no process and no socket of its own outlives the test."""
    repo_root = Path(__file__).resolve().parents[2]
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join([str(repo_root), inherited]).rstrip(os.pathsep)
    )
    worker_handler = WorkerHandler(
        group,
        WORKER_NAME,
        instance_dir=story_root / "i",
        frozen_users_path=story_root / "frozen_users",
        entry_module=ENTRY_MODULE,
        main_threadpool_size=4,
        aux_threadpool_size=1,
        worker_class=DRIVEN_WORKER,
        worker_kwargs={
            "group": GROUP,
            "user_idle_freeze_delay": IDLE_DELAY,
            "transfer_start_delay": GATE_DELAY,
            # Every envelope carries a photo: this story reads what the photo
            # says, and the throttle has its own tests one phase down.
            "worker_snapshot_ttl": 0,
        },
        process_ping_timeout=CALL_TIMEOUT,
    )
    yield worker_handler
    if worker_handler.process is not None and worker_handler.process.poll() is None:
        worker_handler.process.kill()
        worker_handler.process.wait()
    await worker_handler.connector.stop()


async def test_the_worker_is_born_serves_parks_wakes_departs_and_a_successor_takes_over(
    handler, group, deposit, caplog
):
    caplog.set_level(logging.INFO)
    # The fold is Macro 3's: the driver says who the vertex thinks is on board.
    handler.hosted_users.update({"mario", "anna"})

    # BORN. The handler opens the wire and spawns the child, which presents
    # itself with a photo that already knows which process it is — and holds
    # nobody yet.
    await handler.launch_process()
    born = handler.process
    assert handler.connector.connected is True
    assert handler.worker_snapshot["pid"] == born.pid
    assert handler.worker_snapshot["name"] == WORKER_NAME
    assert handler.worker_snapshot["group"] == GROUP
    assert handler.worker_snapshot["user_count"] == 0
    assert handler.worker_snapshot["users"] == {}
    assert handler.worker_snapshot["connections"] == {}

    # SERVES. The request crosses the process boundary inside the envelope and
    # comes back as the site answered it — headers and body whole, and among the
    # headers the whole global store the presentation was answered with. The rows
    # are born on the way in, and the announcements say so.
    before = time.time()
    reply = await handler.connector.call(
        "/site/invoices", http_call("cid-a", "mario", path="/invoices"), timeout=CALL_TIMEOUT
    )

    assert reply["result"]["status"] == 200
    assert ["X-Worker", WORKER_NAME] in reply["result"]["headers"]
    assert ["X-Global-Store", handler.global_register_item_tytx] in reply["result"]["headers"]
    assert body_of(reply) == "GET /invoices for mario"
    assert announced(reply) == ["new_user", "new_connection"]
    photo = reply[WORKER_SNAPSHOT_KEY]
    assert sorted(photo["users"]["mario"]) == ["item", "transfer_flag"]
    assert photo["users"]["mario"]["transfer_flag"] is None
    assert photo["users"]["mario"]["item"]["state"] == "active"
    assert photo["connections"]["cid-a"]["user"] == "mario"
    assert photo["connections"]["cid-a"]["last_rpc_ts"] >= before

    # A second user arrives while the first has gone quiet past the valve's
    # silence: one of them is about to be parked, the other has just spoken.
    await asyncio.sleep(2 * IDLE_DELAY)
    arrival = await handler.connector.call(
        "/site/orders", http_call("cid-b", "anna", path="/orders"), timeout=CALL_TIMEOUT
    )
    assert announced(arrival) == ["new_user", "new_connection"]

    # THE VALVE FLAGS HIM. The driver orders the shot, and the departures are
    # decided inside it: the silent one is ceded because he is idle past the
    # valve's delay — one more reason for a 'T' — and the one who has just
    # spoken is kept. The decision travels on the photo that answers the order.
    planned = await handler.connector.call(PLAN_ORDER, timeout=CALL_TIMEOUT)

    flagged = planned[WORKER_SNAPSHOT_KEY]["users"]
    assert {user: pair["transfer_flag"] for user, pair in flagged.items()} == {
        "mario": "T",
        "anna": None,
    }

    # HE DEPARTS. Past the gate he goes to the deposit like anybody else
    # leaving: the placement the announcement carries is NOBODY'S — the vertex
    # decides where he wakes — and his row leaves memory whole, connection and
    # all. His store and his connection are readable from the parent side.
    parked = await handler.connector.call(EXECUTE_ORDER, timeout=CALL_TIMEOUT)

    assert parked["events"] == [
        {"op": "user_frozen", "worker": WORKER_NAME, "user": "mario", "placement": None}
    ]
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_connection_register_item("mario", "cid-a") is not None
    assert deposit.get_item_header("mario")["writer"] == WORKER_NAME
    photo = parked[WORKER_SNAPSHOT_KEY]
    assert "mario" not in photo["users"]
    assert photo["users"]["anna"]["item"]["state"] == "active"
    assert list(photo["connections"]) == ["cid-b"]

    # WAKES BY VERDICT. His next call carries the verdict, and only that
    # authorises the trip: the store comes home, the connection finds itself in
    # the deposit and is born again through the ordinary announcements, both
    # parcels are taken away and the folder goes with the last of them. WHICH
    # worker he comes home to is the vertex's to say — here it is this one
    # because this story runs a single worker.
    woken = await handler.connector.call(
        "/site/invoices",
        http_call("cid-a", "mario", path="/invoices", user_frozen=True),
        timeout=CALL_TIMEOUT,
    )

    assert announced(woken) == ["user_adopted", "new_connection"]
    assert body_of(woken) == "GET /invoices for mario"
    assert deposit.read_user_register_item("mario") is None
    assert deposit.read_connection_register_item("mario", "cid-a") is None
    assert deposit.user_folders == set()
    assert woken[WORKER_SNAPSHOT_KEY]["users"]["mario"]["item"]["state"] == "active"

    # QUITS ON ORDER. The driver orders the departure, and the reply to that
    # order carries the photo the transfers flagged: everybody ceded, nobody
    # kept. The decision travels in the shot it was taken in.
    leaving = await handler.connector.call(QUIT_ORDER, timeout=CALL_TIMEOUT)

    flags = leaving[WORKER_SNAPSHOT_KEY]["users"]
    assert {user: pair["transfer_flag"] for user, pair in flags.items()} == {
        "mario": "T",
        "anna": "T",
    }
    assert leaving[WORKER_SNAPSHOT_KEY]["user_count"] == 2

    # Past the gate everybody is in the deposit and the process ends BY ITSELF:
    # the exit code is its own clean 0, and nothing in this test killed it. What
    # the freezes would have announced — the placement of each, nobody's — dies
    # with the wire the worker closes behind itself; the flagged photo already
    # said who was leaving, which is what the fold acts on.
    await wait_for(lambda: born.poll() is not None, timeout=DEATH_TIMEOUT)

    assert born.poll() == 0
    assert deposit.user_folders == {
        deposit.user_to_userkey("mario"),
        deposit.user_to_userkey("anna"),
    }
    assert deposit.read_user_register_item("anna") is not None
    assert deposit.read_connection_register_item("anna", "cid-b") is not None
    assert deposit.lock_holder("mario") is None
    assert deposit.lock_holder("anna") is None

    # THE DECLARED SEAM. In Macro 2 that departure is still a WILD death: the
    # handler marks a death governed only when IT ordered the relaunch, and
    # nothing here reads the intent the worker announced. So the group is told
    # of an abort, carrying the handler and the users the vertex had on board.
    # The governed mark arrives in Macro 3, with the group that reads the photo.
    await wait_for(lambda: group.aborted == [handler])
    assert group.users_on_board == [{"mario", "anna"}]
    assert "WILD death" in caplog.text
    assert handler.connector.connected is False

    # RELAUNCH. The same handler launches a successor on the same name and the
    # same socket: it presents itself with a fresh photo of its own process,
    # holding nobody. The deposit is untouched by the rebirth — the parcels are
    # where the dead one left them, waiting for whoever will be told to take
    # them. This is the picture Macro 3 inherits.
    await handler.launch_process()

    assert handler.process.pid != born.pid
    assert handler.connector.connected is True
    assert handler.worker_snapshot["pid"] == handler.process.pid
    assert handler.worker_snapshot["user_count"] == 0
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_user_register_item("anna") is not None
