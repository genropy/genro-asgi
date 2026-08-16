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

"""SpaWorker on the wire: the shell, the envelopes, the photo, the self-defense.

Everything here is real except the level above the wire: a real Unix socket, the
package's own connector and frames, the package's own ``WorkerEntry`` running
the worker exactly as the spawned child does — it is only run on this same loop
instead of in another process, which is what makes the story watchable step by
step. What is doubled is the handler above the connector, because the
GroupHandler and the Commander are Macro 3's.

The last test spawns a REAL child through the M1 ``WorkerHandler``, and there the
entry is the process it is meant to be: the site answers over the wire, the wire
is then taken away, and what the orphan does about its users is read back from
the deposit on disk.

The sockets and the deposit live under a short ``mkdtemp`` root: the system caps
a UDS path at about a hundred characters and pytest's own directory is already
past it.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from genro_asgi.channel.frame import Frame, FrameStream
from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker, WorkerEntry, WorkerHandler
from genro_asgi.spa.orchestration.worker_connector import (
    CALL_METHOD,
    GLOBAL_STORE_KEY,
    REPLY_METHOD,
    WORKER_SNAPSHOT_KEY,
    WorkerConnector,
)
from genro_asgi.spa.orchestration.worker_entry import DEFAULT_WORKER_CLASS
from genro_asgi.spa.orchestration.worker_handler import PING_OP_PATH, WORKER_ENV_VAR

WORKER_NAME = "standard_0001"
GROUP = "standard"
ENTRY_MODULE = "genro_asgi.spa.orchestration.worker_entry"
ECHO_WORKER = f"{__name__}:EchoWorker"
GLOBAL_STORE = "the whole global store, as it travels"
LONG_TTL = 30.0
BROKEN_PATH = "/falls_over"


class EchoWorker(SpaWorker):
    """A worker hosting one tiny WSGI site: the seam a subclass fills, played here.

    The real filler is the genropy-asgi bridge, whose worker mounts a whole
    site. This one answers with the facts of the request, which is all a test
    needs to know the environ was synthesized and the answer came back whole.
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.wsgi_app = self.echo_site

    def echo_site(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        """The WSGI callable: say back who asked, and for what — or break on demand."""
        if environ["PATH_INFO"] == BROKEN_PATH:
            raise RuntimeError("the site fell over")
        start_response("200 OK", [("Content-Type", "text/plain"), ("X-Worker", self.name)])
        return [f"{environ['REQUEST_METHOD']} {environ['PATH_INFO']} "
                f"for {environ['genro.identity']}".encode()]


class HandlerStub:
    """The WorkerHandler seen from the wire: the store it answers, what it is told."""

    def __init__(self) -> None:
        self.global_register_item_tytx = GLOBAL_STORE
        self.worker_snapshot: dict[str, Any] | None = None
        self.messages: list[Frame] = []
        self.lost = 0

    def on_child_message(self, frame: Frame) -> None:
        self.messages.append(frame)

    def on_child_lost(self) -> None:
        self.lost += 1


class Wire:
    """One worker's socket with its handler above it, both on this same loop.

    ``take`` runs the package's own ``WorkerEntry`` against this socket, so what
    is under test is the very shell the spawned child runs — its worker is
    reachable afterwards for the assertions the wire alone cannot make.
    """

    def __init__(self, socket_path: Path, deposit_path: Path) -> None:
        self.socket_path = socket_path
        self.deposit_path = deposit_path
        self.handler = HandlerStub()
        self.connector = WorkerConnector(self.handler, socket_path)
        self.entries: list[WorkerEntry] = []
        self.lives: list[asyncio.Task[None]] = []

    def spawn_config(self, worker_class: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """The seven-key payload, exactly as a WorkerHandler writes it."""
        return {
            "name": WORKER_NAME,
            "uds_url": self.connector.address,
            "frozen_users_path": str(self.deposit_path),
            "main_threadpool_size": 4,
            "aux_threadpool_size": 1,
            "worker_class": worker_class,
            "kwargs": {"group": GROUP, "worker_snapshot_ttl": LONG_TTL, **kwargs},
        }

    async def start(self) -> None:
        await self.connector.start()

    async def take(self, worker_class: str = ECHO_WORKER, **kwargs: Any) -> SpaWorker:
        """Run one worker's whole life against this wire, and hand it over."""
        entry = WorkerEntry(config=self.spawn_config(worker_class, kwargs))
        self.entries.append(entry)
        self.lives.append(asyncio.create_task(entry.serve()))
        await wait_for(lambda: self.connector.connected)
        return entry.worker

    async def stop(self) -> None:
        """Close the wire and let every worker on it finish its own end."""
        await self.connector.stop()
        for life in self.lives:
            life.cancel()
            try:
                await life
            except asyncio.CancelledError:
                pass


class ParentWire:
    """A parent that answers whatever the worker CALLs: the road upward, bare.

    The connector has no consumer for a CALL coming up — that is Macro 3's — so
    the one thing this test double does is answer, which is what the worker's
    inline REPLY resolution needs to be proven at all.
    """

    def __init__(self, socket_path: Path, deposit_path: Path) -> None:
        self.socket_path = socket_path
        self.deposit_path = deposit_path
        self.calls: list[Frame] = []
        self.answering = True
        self.server: asyncio.Server | None = None
        self.stream: FrameStream | None = None
        self.entries: list[WorkerEntry] = []
        self.lives: list[asyncio.Task[None]] = []

    @property
    def address(self) -> str:
        return f"uds:{self.socket_path}"

    async def start(self) -> None:
        self.server = await asyncio.start_unix_server(self.serve, path=str(self.socket_path))

    async def take(self) -> SpaWorker:
        """Run one worker's life against this parent, and hand it over presented."""
        entry = WorkerEntry(
            config={
                "name": WORKER_NAME,
                "uds_url": self.address,
                "frozen_users_path": str(self.deposit_path),
                "main_threadpool_size": 2,
                "aux_threadpool_size": 1,
                "worker_class": ECHO_WORKER,
                "kwargs": {"group": GROUP, "worker_snapshot_ttl": 0},
            }
        )
        self.entries.append(entry)
        self.lives.append(asyncio.create_task(entry.serve()))
        await wait_for(lambda: entry.worker is not None and entry.worker.global_register_item_tytx)
        return entry.worker

    async def stop(self) -> None:
        """Let the workers go first: a server waits for the connections it holds."""
        for life in self.lives:
            life.cancel()
            try:
                await life
            except asyncio.CancelledError:
                pass
        if self.stream is not None:
            await self.stream.close()
        self.server.close()
        await self.server.wait_closed()

    async def send_nonsense(self) -> None:
        """Write something that is not a wsx envelope: the protocol violation drill."""
        payload = b"this is not a wsx envelope"
        self.stream.writer.write(len(payload).to_bytes(4, "big") + payload)
        await self.stream.writer.drain()

    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        stream = self.stream = FrameStream(reader, writer)
        while True:
            frame = await stream.read()
            if frame is None:
                return
            if frame.method == CALL_METHOD:
                self.calls.append(frame)
                if not self.answering:
                    continue
                data: dict[str, Any] = {"result": "heard"}
            else:
                data = {GLOBAL_STORE_KEY: GLOBAL_STORE}
            await stream.write(
                Frame(id=frame.id, method=REPLY_METHOD, path=frame.path, data=data)
            )


async def wait_for(condition, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("the worker never reached the awaited state")
        await asyncio.sleep(0.01)


def http_call(
    cid: str, identity: str | None = None, *, path: str = "/invoices", **payload: Any
) -> dict[str, Any]:
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
        "identity": identity or cid,
        **payload,
    }


def body_of(reply: dict[str, Any]) -> str:
    """The WSGI answer's body, decoded out of the wire form."""
    return base64.b64decode(reply["result"]["body"]).decode()


def announced(reply: dict[str, Any]) -> list[str]:
    """The protocol names the reply carried up, in order."""
    return [event["op"] for event in reply["events"]]


@pytest.fixture
def wire_root():
    """The short root holding the socket directory and the deposit."""
    root = Path(tempfile.mkdtemp(prefix="gnrwire_"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def deposit(wire_root):
    """The deposit as the parent side reads it — the same root the worker is given."""
    return FreezeHandler(wire_root / "frozen_users")


@pytest.fixture
async def wire(wire_root, deposit):
    one = Wire(wire_root / "w.sock", wire_root / "frozen_users")
    await one.start()
    yield one
    await one.stop()


@pytest.fixture
async def parent_wire(wire_root, deposit):
    parent = ParentWire(wire_root / "p.sock", wire_root / "frozen_users")
    await parent.start()
    yield parent
    await parent.stop()


# ----------------------------------------------------------------------
# The presentation: a live process has a photo, and the store on board
# ----------------------------------------------------------------------


async def test_the_presentation_carries_the_first_photo_and_brings_the_store_home(wire):
    worker = await wire.take()

    assert wire.handler.worker_snapshot == {
        "pid": os.getpid(),
        "name": WORKER_NAME,
        "group": GROUP,
        "rss_bytes": worker.rss_bytes,
        "user_count": 0,
        "connection_count": 0,
        "page_count": 0,
        "connections": {},
        "users": {},
    }
    assert worker.global_register_item_tytx == GLOBAL_STORE


async def test_the_beat_is_answered_and_asks_for_nothing_else(wire):
    await wire.take()

    reply = await wire.connector.call(PING_OP_PATH, timeout=5.0)

    assert reply["result"] == {}
    assert reply["events"] == []


async def test_an_op_nobody_here_knows_is_refused_by_name(wire):
    await wire.take()

    reply = await wire.connector.call("/op/nothing_of_the_kind", timeout=5.0)

    assert reply["error"] == "unknown op: '/op/nothing_of_the_kind'"


# ----------------------------------------------------------------------
# The http form: the row first, the site after
# ----------------------------------------------------------------------


async def test_an_http_call_is_served_by_the_site_the_subclass_assigned(wire):
    await wire.take()

    reply = await wire.connector.call(
        "/site/invoices", http_call("cid-a", "mario"), timeout=5.0
    )

    assert reply["result"]["status"] == 200
    assert ["X-Worker", WORKER_NAME] in reply["result"]["headers"]
    assert body_of(reply) == "GET /invoices for mario"


async def test_the_request_finds_its_row_born_and_its_clocks_stamped(wire):
    worker = await wire.take()
    before = time.time()

    reply = await wire.connector.call(
        "/site/invoices", http_call("cid-a", "mario"), timeout=5.0
    )

    assert announced(reply) == ["new_user", "new_connection"]
    assert worker.connection_register["cid-a"]["user"] == "mario"
    assert worker.user_register["mario"]["state"] == "active"
    assert worker.user_register["mario"]["last_rpc_ts"] >= before
    assert worker.connection_register["cid-a"]["last_rpc_ts"] >= before


async def test_an_anonymous_request_is_a_guest_in_full(wire):
    worker = await wire.take()

    await wire.connector.call("/site/invoices", http_call("cid-a"), timeout=5.0)

    assert worker.connection_register["cid-a"]["user"] == "guest_cid-a"
    assert "guest_cid-a" in worker.user_register


async def test_the_second_request_of_a_connection_costs_no_new_row(wire):
    worker = await wire.take()
    await wire.connector.call("/site/invoices", http_call("cid-a", "mario"), timeout=5.0)

    reply = await wire.connector.call(
        "/site/invoices", http_call("cid-a", "mario"), timeout=5.0
    )

    assert announced(reply) == []
    assert list(worker.user_register) == ["mario"]


async def test_a_frozen_user_comes_home_when_the_envelope_says_so(wire, deposit):
    worker = await wire.take()
    await wire.connector.call("/site/invoices", http_call("cid-a", "mario"), timeout=5.0)
    await worker.freeze_user("mario")
    assert deposit.read_user_register_item("mario") is not None

    reply = await wire.connector.call(
        "/site/invoices", http_call("cid-a", "mario", user_frozen=True), timeout=5.0
    )

    assert "user_adopted" in announced(reply)
    assert worker.user_register["mario"]["state"] == "active"
    assert deposit.read_user_register_item("mario") is None


async def test_a_site_that_falls_over_answers_with_its_failure_and_frees_the_user(wire):
    worker = await wire.take()

    reply = await wire.connector.call(
        "/site/falls_over", http_call("cid-a", "mario", path=BROKEN_PATH), timeout=5.0
    )

    assert reply["error"] == "RuntimeError: the site fell over"
    assert await worker.freeze_user("mario") is True


async def test_a_request_that_names_no_connection_is_answered_with_its_failure(wire):
    await wire.take()
    payload = http_call("cid-a", "mario")
    del payload["http"]["cid"]

    reply = await wire.connector.call("/site/invoices", payload, timeout=5.0)

    assert reply["error"] == "KeyError: 'cid'"


async def test_a_worker_with_no_site_refuses_the_form_and_registers_nobody(wire):
    worker = await wire.take(f"{SpaWorker.__module__}:SpaWorker")

    reply = await wire.connector.call(
        "/site/invoices", http_call("cid-a", "mario"), timeout=5.0
    )

    assert reply["error"] == "http CALL form refused: this worker hosts no WSGI site"
    assert worker.user_register == {}


# ----------------------------------------------------------------------
# The photo: from birth, on a change, and never twice inside the ttl
# ----------------------------------------------------------------------


async def test_two_replies_inside_the_ttl_carry_one_photo(wire):
    await wire.take(worker_snapshot_ttl=0.05)
    await asyncio.sleep(0.06)

    first = await wire.connector.call(PING_OP_PATH, timeout=5.0)
    second = await wire.connector.call(PING_OP_PATH, timeout=5.0)
    await asyncio.sleep(0.06)
    third = await wire.connector.call(PING_OP_PATH, timeout=5.0)

    assert WORKER_SNAPSHOT_KEY in first
    assert WORKER_SNAPSHOT_KEY not in second
    assert third[WORKER_SNAPSHOT_KEY]["pid"] == first[WORKER_SNAPSHOT_KEY]["pid"]


async def test_a_user_arriving_puts_the_photo_on_the_envelope_whatever_the_ttl(wire):
    await wire.take()
    await wire.connector.call(PING_OP_PATH, timeout=5.0)

    arrival = await wire.connector.call(
        "/site/invoices", http_call("cid-a", "mario"), timeout=5.0
    )
    quiet = await wire.connector.call(PING_OP_PATH, timeout=5.0)

    assert arrival[WORKER_SNAPSHOT_KEY]["users"]["mario"] == {
        "item": arrival[WORKER_SNAPSHOT_KEY]["users"]["mario"]["item"],
        "transfer_flag": None,
    }
    assert arrival[WORKER_SNAPSHOT_KEY]["user_count"] == 1
    assert WORKER_SNAPSHOT_KEY not in quiet


async def test_a_user_leaving_puts_the_photo_on_the_envelope_too(wire):
    worker = await wire.take()
    await wire.connector.call("/site/invoices", http_call("cid-a", "mario"), timeout=5.0)
    await wire.connector.call(PING_OP_PATH, timeout=5.0)
    worker.plan_transfers(transfer_users=["mario"])

    await worker.freeze_user("mario")
    reply = await wire.connector.call(PING_OP_PATH, timeout=5.0)

    assert announced(reply) == ["user_frozen"]
    assert reply[WORKER_SNAPSHOT_KEY]["user_count"] == 0


async def test_the_photo_carries_the_flag_the_transfers_decided(wire):
    worker = await wire.take(worker_snapshot_ttl=0)
    await wire.connector.call("/site/invoices", http_call("cid-a", "mario"), timeout=5.0)
    worker.plan_transfers(transfer_users=["mario"])

    reply = await wire.connector.call(PING_OP_PATH, timeout=5.0)

    photo = reply[WORKER_SNAPSHOT_KEY]
    assert photo["users"]["mario"]["transfer_flag"] == "T"
    assert photo["users"]["mario"]["item"]["state"] == "active"
    assert photo["users"]["mario"]["item"]["connection_count"] == 1
    assert photo["connections"]["cid-a"]["user"] == "mario"


# ----------------------------------------------------------------------
# The store downward, and the road upward
# ----------------------------------------------------------------------


async def test_the_store_slot_replaces_the_replica_whole(wire):
    worker = await wire.take()
    assert worker.global_register_item_tytx == GLOBAL_STORE

    await wire.connector.send_event("/anything", {GLOBAL_STORE_KEY: "a later store"})

    await wait_for(lambda: worker.global_register_item_tytx == "a later store")


async def test_a_call_of_the_worker_is_resolved_by_the_reply_that_answers_it(parent_wire):
    worker = await parent_wire.take()

    answer = await worker.call("/op/anything", {"asked": "something"})

    assert answer == {"result": "heard"}
    assert parent_wire.calls[0].data["asked"] == "something"
    assert parent_wire.calls[0].data[WORKER_SNAPSHOT_KEY]["name"] == WORKER_NAME


async def test_a_call_in_flight_when_the_wire_dies_is_failed_not_forgotten(parent_wire):
    worker = await parent_wire.take()
    parent_wire.answering = False
    asking = asyncio.create_task(worker.call("/op/anything"))
    await wait_for(lambda: parent_wire.calls)

    await parent_wire.stream.close()

    with pytest.raises(ConnectionError):
        await asking


async def test_a_reply_nobody_is_waiting_for_is_dropped(wire):
    worker = await wire.take()

    worker.handle_frame(Frame(id="never-asked", method=REPLY_METHOD, path="/op/anything"))

    assert worker.exited is False


async def test_an_envelope_of_no_known_kind_is_denounced_and_nothing_else(wire, caplog):
    caplog.set_level(logging.WARNING)
    worker = await wire.take()

    worker.handle_frame(Frame(method="POST", path="/op/anything"))

    assert "unexpected envelope POST" in caplog.text


async def test_a_violation_of_the_protocol_ends_the_wire_like_a_death(parent_wire):
    worker = await parent_wire.take()

    await parent_wire.send_nonsense()

    await wait_for(lambda: worker.exited)


# ----------------------------------------------------------------------
# The self-defense: a wire gone is everybody into the deposit
# ----------------------------------------------------------------------


async def test_a_dead_wire_parks_everybody_in_the_deposit_and_ends_the_worker(wire, deposit):
    worker = await wire.take()
    await wire.connector.call("/site/invoices", http_call("cid-a", "mario"), timeout=5.0)

    await wire.connector.stop()

    await wait_for(lambda: worker.exited)
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_connection_register_item("mario", "cid-a") is not None
    assert worker.user_register == {}


# ----------------------------------------------------------------------
# The spawn contract: what the shell refuses to guess
# ----------------------------------------------------------------------


def test_a_spawn_without_its_payload_is_a_contract_violation(monkeypatch):
    monkeypatch.delenv(WORKER_ENV_VAR, raising=False)

    with pytest.raises(SystemExit, match="is not set"):
        WorkerEntry()


def test_a_payload_that_is_not_an_object_is_refused_by_what_it_is(monkeypatch):
    monkeypatch.setenv(WORKER_ENV_VAR, "not json at all")
    with pytest.raises(SystemExit, match="not valid JSON"):
        WorkerEntry()

    monkeypatch.setenv(WORKER_ENV_VAR, '["a", "list"]')
    with pytest.raises(SystemExit, match="must be a JSON object"):
        WorkerEntry()


def test_a_payload_short_of_a_key_says_which_one(monkeypatch):
    monkeypatch.setenv(WORKER_ENV_VAR, '{"name": "standard_0001"}')

    with pytest.raises(SystemExit, match="missing uds_url, frozen_users_path"):
        WorkerEntry()


def test_the_payload_is_read_from_the_environment_the_handler_wrote(monkeypatch, wire_root):
    monkeypatch.setenv(
        WORKER_ENV_VAR,
        json.dumps(
            {
                "name": WORKER_NAME,
                "uds_url": "uds:/nowhere.sock",
                "frozen_users_path": str(wire_root / "frozen_users"),
                "main_threadpool_size": 8,
                "aux_threadpool_size": 2,
                "worker_class": None,
                "kwargs": {"group": GROUP},
            }
        ),
    )

    entry = WorkerEntry()

    assert entry.name == WORKER_NAME
    assert entry.main_threadpool_size == 8
    assert entry.aux_threadpool_size == 2
    assert entry.worker_class == DEFAULT_WORKER_CLASS


def test_a_worker_class_that_is_not_a_reference_is_refused(wire_root):
    entry = WorkerEntry(
        config={
            "name": WORKER_NAME,
            "uds_url": "uds:/nowhere.sock",
            "frozen_users_path": str(wire_root / "frozen_users"),
            "worker_class": "genro_asgi.spa.orchestration.spa_worker.SpaWorker",
        }
    )

    with pytest.raises(SystemExit, match="module.path:ClassName"):
        entry.build_worker()


def test_the_payload_naming_no_class_builds_the_worker_of_the_house(wire_root):
    entry = WorkerEntry(
        config={
            "name": WORKER_NAME,
            "uds_url": "uds:/nowhere.sock",
            "frozen_users_path": str(wire_root / "frozen_users"),
            "kwargs": {"group": GROUP},
        }
    )

    worker = entry.build_worker()

    assert type(worker) is SpaWorker
    assert worker.group == GROUP
    assert worker.freeze_handler.root_path == wire_root / "frozen_users"


# ----------------------------------------------------------------------
# The same story in a real child process
# ----------------------------------------------------------------------


@pytest.fixture
async def handler(wire_root, monkeypatch):
    """A real WorkerHandler spawning the real entry; nothing of it outlives the test."""
    repo_root = Path(__file__).resolve().parents[2]
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join([str(repo_root), inherited]).rstrip(os.pathsep)
    )
    worker_handler = WorkerHandler(
        HandlerStub(),
        WORKER_NAME,
        instance_dir=wire_root / "i",
        frozen_users_path=wire_root / "frozen_users",
        entry_module=ENTRY_MODULE,
        main_threadpool_size=4,
        aux_threadpool_size=1,
        worker_class=ECHO_WORKER,
        worker_kwargs={"group": GROUP},
        process_ping_timeout=10.0,
    )
    yield worker_handler
    if worker_handler.process is not None and worker_handler.process.poll() is None:
        worker_handler.process.kill()
        worker_handler.process.wait()
    await worker_handler.connector.stop()


async def test_a_real_child_serves_its_site_and_saves_its_users_when_the_wire_goes(
    handler, deposit
):
    # It is born in a process of its own, and presents itself with a photo that
    # already knows it is that process: the pid is the one the handler spawned.
    await handler.launch_process()
    assert handler.worker_snapshot["pid"] == handler.process.pid
    assert handler.worker_snapshot["user_count"] == 0

    # It is alive, and it serves: the request crosses the process boundary
    # emulated in the envelope and comes back as the site answered it.
    await handler.ping_process()
    reply = await handler.connector.call(
        "/site/invoices", http_call("cid-a", "mario"), timeout=10.0
    )
    assert body_of(reply) == "GET /invoices for mario"
    assert announced(reply) == ["new_user", "new_connection"]

    # The wire is taken away under it. Nobody can be told anything any more, so
    # it parks its user in the deposit — the road that never passed through the
    # channel — and ends its process by itself.
    await handler.connector.stop()

    await wait_for(lambda: handler.process.poll() is not None, timeout=15.0)
    assert handler.process.poll() == 0
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_connection_register_item("mario", "cid-a") is not None
    assert deposit.lock_holder("mario") is None
