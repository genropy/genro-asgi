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

"""UserStickyWorker tests: the causal envelope and the idle outbox.

The worker is exercised over a real wire (a ``LocalChannel`` attached to a
``ChannelHub``), so a CALL is serviced exactly as it will be in production:
the op runs on its own vehicle — a sync handler off the loop, a coroutine on
it — and the REPLY carries the events THAT CALL caused, which the hub folds
before resolving the caller. The outbox and its sender task stay wired with no
producer: the tests assert both that they still ship what is offered to them
and that no lifecycle op ever offers anything.

A lifecycle op outside a CALL is an impossible case, so the unit-level tests
open the same sink ``service_call`` opens, through ``call_sink``.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import pytest
from genro_routes import route

from genro_asgi.channel import ChannelCallError, ChannelHub, Frame, LocalChannel
from genro_asgi.channel.hub import CALL_METHOD
from genro_asgi.spa import RegisterRegistry
from genro_asgi.spa.worker import (
    EXCHANGE_OPS,
    LIFECYCLE_OPS,
    POST_OPS,
    STORE_OPS,
    Outbox,
    UserStickyWorker,
)


@contextmanager
def call_sink(worker: UserStickyWorker) -> Iterator[list[dict[str, Any]]]:
    """Open the sink a CALL would open and hand back what the ops append to it."""
    events: list[dict[str, Any]] = []
    token = worker._call_events.set(events)
    try:
        yield events
    finally:
        worker._call_events.reset(token)


class RecordingChannel:
    """The member face reduced to what ``send_reply`` needs: it keeps the frames."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []
        self.on_message: Any = None

    async def send_frame(self, frame: Frame) -> str:
        self.frames.append(frame)
        return frame.id

    async def close(self) -> None:
        pass


class ProbeWorker(UserStickyWorker):
    """A worker with one sync and one async op, each recording its thread."""

    def __init__(self, name: str, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.threads: dict[str, str] = {}
        self.gate = threading.Event()
        self.async_gate = asyncio.Event()
        self.entered = asyncio.Event()

    @route()
    def sync_probe(self, identity: str, value: int = 0) -> dict[str, Any]:
        self.threads["sync_probe"] = threading.current_thread().name
        return {"identity": identity, "value": value}

    @route()
    async def async_probe(self, identity: str) -> dict[str, Any]:
        self.threads["async_probe"] = threading.current_thread().name
        return {"identity": identity}

    @route()
    def gated_user(self, identity: str) -> dict[str, Any]:
        """Create the user, then hold this CALL open until the gate is released."""
        entry = self.new_user(identity)
        self.gate.wait(timeout=5.0)
        return entry

    @route()
    async def gated_async_user(self, identity: str) -> dict[str, Any]:
        """Create the user on the loop, then park this CALL on the async gate."""
        entry = self.new_user(identity)
        self.entered.set()
        await self.async_gate.wait()
        return entry

    @route()
    def boom(self, identity: str) -> None:
        raise RuntimeError("handler exploded")


class WorkerHarness:
    """A worker on a LocalChannel attached to a hub, with the fold recorded."""

    def __init__(self, worker: UserStickyWorker) -> None:
        self.worker = worker
        self.folded: list[list[dict[str, Any]]] = []
        self.events: list[Frame] = []
        self.hub = ChannelHub(on_event=self._on_event)
        self.channel = LocalChannel(worker.name)

    async def start(self) -> None:
        await self.hub.start()
        self.worker.attach_channel(self.channel)
        await self.channel.connect()
        await self.hub.attach_local(self.channel)

    async def stop(self) -> None:
        await self.worker.shutdown()
        await self.hub.stop()

    async def call(self, path: str, data: Any) -> Any:
        """CALL the worker and read the payload the way the commander does."""
        payload = await self.hub.call(self.worker.name, path, data, timeout=5.0)
        self.folded.append(payload.get("events") or [])
        if "error" in payload:
            raise ChannelCallError(self.worker.name, path, payload["error"])
        return payload.get("result")

    async def wait_events(self, count: int, timeout: float = 5.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while len(self.events) < count:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"got {len(self.events)}/{count} EVENTs")
            await asyncio.sleep(0.01)

    def _on_event(self, member: Any, frame: Frame) -> None:
        self.events.append(frame)


@pytest.fixture
async def harness() -> Any:
    probe = WorkerHarness(ProbeWorker("W:w1"))
    await probe.start()
    try:
        yield probe
    finally:
        await probe.stop()


# ----------------------------------------------------------------------
# Outbox — offer/drain/ack, at-least-once
# ----------------------------------------------------------------------


def test_outbox_drain_returns_snapshot_until_acked() -> None:
    outbox = Outbox(worker=None)  # type: ignore[arg-type]
    outbox.offer({"op": "new_user", "seq": 1})
    outbox.offer({"op": "new_user", "seq": 2})
    assert [e["seq"] for e in outbox.drain()] == [1, 2]
    # Not acked: the same snapshot comes back — at-least-once.
    assert [e["seq"] for e in outbox.drain()] == [1, 2]
    assert outbox.pending() == 2
    assert outbox.ping_now is True


def test_outbox_ack_keeps_events_queued_while_the_batch_was_in_flight() -> None:
    outbox = Outbox(worker=None)  # type: ignore[arg-type]
    outbox.offer({"op": "new_user", "seq": 1})
    outbox.offer({"op": "new_user", "seq": 2})
    shipped = outbox.drain()
    # A third event is born while the batch is on the wire.
    outbox.offer({"op": "drop_user", "seq": 3})
    remaining = outbox.drain(shipped[-1]["seq"])
    assert [e["seq"] for e in remaining] == [3]
    assert outbox.acked_seq == 2
    # A stale ack never resurrects nor re-drops anything.
    assert [e["seq"] for e in outbox.drain(1)] == [3]
    assert outbox.acked_seq == 2


def test_outbox_offer_wakes_the_notify_callback() -> None:
    outbox = Outbox(worker=None)  # type: ignore[arg-type]
    woken: list[int] = []
    outbox.notify = lambda: woken.append(outbox.pending())
    outbox.offer({"op": "new_user", "seq": 1})
    assert woken == [1]


# ----------------------------------------------------------------------
# Op vocabulary
# ----------------------------------------------------------------------


def test_op_vocabulary_is_the_whole_reserved_set() -> None:
    assert "change_connection_user" in LIFECYCLE_OPS
    assert len(LIFECYCLE_OPS) == 9
    assert STORE_OPS == frozenset({"store_set", "store_del", "store_lock", "store_unlock"})
    assert POST_OPS == frozenset({"subscribeTable", "notifyDbEvents"})
    assert len(EXCHANGE_OPS) == 3
    worker = UserStickyWorker("W:w1")
    # The exchange names are served (the addressed write), the post ones too (the
    # dbevents species), and so are the two global-store writes. The lock pair is
    # the exception BY DESIGN: those two names exist only as the ascending
    # handshake ``global_store_lock`` produces, so no CALL ever addresses them.
    assert worker.op_names >= EXCHANGE_OPS | POST_OPS | {"store_set", "store_del"}
    assert not worker.op_names & {"store_lock", "store_unlock"}


# ----------------------------------------------------------------------
# Lifecycle ops — register mutation plus a shaped event
# ----------------------------------------------------------------------


def test_lifecycle_ops_mutate_the_register_and_shape_increasing_seqs() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker) as events:
        worker.new_connection("sess-1")
        assert worker.connection_items.get("sess-1")["user"] == "sess-1"

        entry = worker.change_connection_user("sess-1", user="alice", tenant="acme")
        # The login's own fields describe the real user, so they are on the entry
        # it creates — and then it is pushed out: the login event takes the
        # baggage and this worker keeps neither key.
        assert entry["tenant"] == "acme"
        assert entry["register_item_id"] == "alice"
        assert "sess-1" not in worker.user_items
        assert "alice" not in worker.user_items

        worker.install_package("alice", events[-1]["package"])
        worker.drop_user("alice")
        assert "alice" not in worker.user_items

        assert [(e["op"], e["seq"]) for e in events] == [
            ("new_user", 1),
            ("new_connection", 2),
            ("change_connection_user", 3),
            ("drop_user", 4),
        ]
        assert {e["worker"] for e in events} == {"W:w1"}
        assert events[2]["previous_user"] == "sess-1"
        assert events[2]["user"] == "alice"
        assert events[2]["session_id"] == "sess-1"
    assert worker.last_seq == 4
    # The lifecycle never touches the outbox: it rides the REPLY alone.
    assert worker.outbox.pending() == 0


def test_the_page_ops_announce_the_whole_chain_cascade_in_order() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker) as events:
        worker.new_page("sess-1", "p1", session_id="sess-1")
        worker.new_page("sess-1", "p2", session_id="sess-1")
        assert [(e["op"], e.get("session_id"), e.get("page_id")) for e in events] == [
            ("new_user", None, None),
            ("new_connection", "sess-1", None),
            ("new_page", "sess-1", "p1"),
            ("new_page", "sess-1", "p2"),
        ]
        events.clear()
        worker.drop_page("sess-1", "p1")
        worker.drop_page("sess-1", "p2")
        assert [(e["op"], e.get("session_id"), e.get("page_id")) for e in events] == [
            ("drop_page", None, "p1"),
            ("drop_page", None, "p2"),
            ("drop_connection", "sess-1", None),
            ("drop_user", None, None),
        ]
    assert len(worker.connection_items) == 0


def test_a_second_connection_of_a_user_announces_only_its_own_birth() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker) as events:
        worker.new_page("alice", "p1", session_id="sess-1")
        events.clear()
        worker.new_page("alice", "p2", session_id="sess-2")
        assert [(e["op"], e.get("session_id")) for e in events] == [
            ("new_connection", "sess-2"),
            ("new_page", "sess-2"),
        ]
        events.clear()
        worker.drop_page("alice", "p1")
        # The sibling connection keeps the user alive: no drop_user in the cascade.
        assert [(e["op"], e.get("session_id")) for e in events] == [
            ("drop_page", None),
            ("drop_connection", "sess-1"),
        ]
    assert worker.user_items.get("alice")["connections"] == {"sess-2"}


def test_a_connection_row_survives_the_wire_view() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker):
        worker.new_page("alice", "p1", session_id="sess-1")
    wired = worker.wire_entry(worker.connection_items.get("sess-1"))
    assert wired == {"register_item_id": "sess-1", "user": "alice"}


def test_a_lifecycle_op_outside_a_call_is_an_explicit_error() -> None:
    worker = UserStickyWorker("W:w1")
    with pytest.raises(RuntimeError, match="outside a CALL"):
        worker.new_user("alice")


def test_change_connection_user_on_an_unknown_identity_is_an_explicit_error() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker), pytest.raises(KeyError):
        worker.change_connection_user("ghost", user="alice")


def test_operational_ops_shape_no_event() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker) as events:
        worker.new_connection("sess-1")
        worker.change_connection_user("sess-1", user="alice")
        package = events[-1]["package"]
        worker.install_package("alice", package)
        assert [e["op"] for e in events] == [
            "new_user",
            "new_connection",
            "change_connection_user",
        ]
    assert worker.shape_event("install_package", user="alice") is None


# ----------------------------------------------------------------------
# The install primitives — the push round-trip preserves the entry
# ----------------------------------------------------------------------


def test_the_login_push_round_trip_preserves_the_user_entry() -> None:
    source = UserStickyWorker("W:w1")
    target = UserStickyWorker("W:w2")
    with call_sink(source) as events:
        source.new_connection("sess-1")
        entry = source.change_connection_user(
            "sess-1", user="alice", tenant="acme", tags=["admin"]
        )
        # The source spends and forgets: the slice lives on in the package alone.
        assert "alice" not in source.user_items
        package = events[-1]["package"]

    installed = target.install_package("alice", package)
    assert installed["tenant"] == "acme"
    assert installed["tags"] == ["admin"]
    assert installed["register_item_id"] == "alice"
    # An op answers with the wire view: the live store stays on the worker.
    assert target.wire_entry(target.user_items.get("alice")) == installed
    # The package is a deepcopy: the source's own entry never reached it.
    assert installed is not entry


def test_add_user_refuses_a_package_addressed_to_another_identity() -> None:
    source = UserStickyWorker("W:w1")
    target = UserStickyWorker("W:w2")
    with call_sink(source) as events:
        source.new_connection("sess-1")
        source.change_connection_user("sess-1", user="alice")
        package = events[-1]["package"]
    with pytest.raises(ValueError, match="addressed to"):
        target.install_package("bob", package)


# ----------------------------------------------------------------------
# CALL servicing over the wire
# ----------------------------------------------------------------------


async def test_call_on_a_sync_handler_runs_off_the_loop(harness: WorkerHarness) -> None:
    result = await harness.call("/op/sync_probe", {"identity": "alice", "kwargs": {"value": 7}})
    assert result == {"identity": "alice", "value": 7}
    assert harness.worker.threads["sync_probe"].startswith("genro-pool")


async def test_call_on_an_async_handler_runs_on_the_loop(harness: WorkerHarness) -> None:
    result = await harness.call("/op/async_probe", {"identity": "alice"})
    assert result == {"identity": "alice"}
    assert harness.worker.threads["async_probe"] == threading.current_thread().name


async def test_the_reply_carries_the_events_its_own_call_caused(
    harness: WorkerHarness,
) -> None:
    entry = await harness.call("/op/new_user", {"identity": "alice", "kwargs": {"tenant": "acme"}})
    assert entry["register_item_id"] == "alice"
    assert [e["op"] for e in harness.folded[0]] == ["new_user"]
    assert harness.folded[0][0]["seq"] == 1
    # The lifecycle rides the REPLY alone; the outbox never sees it.
    assert harness.worker.outbox.pending() == 0
    # The next REPLY carries only what its own call caused.
    await harness.call("/op/drop_user", {"identity": "alice"})
    assert [e["op"] for e in harness.folded[1]] == ["drop_user"]


async def test_a_call_that_causes_nothing_replies_with_an_empty_envelope(
    harness: WorkerHarness,
) -> None:
    await harness.call("/op/async_probe", {"identity": "alice"})
    assert harness.folded[0] == []


async def test_two_calls_in_flight_keep_their_envelopes_apart() -> None:
    """The sink is per-context: an overlapping CALL never lands in this envelope."""
    worker = ProbeWorker("W:w1")
    channel = RecordingChannel()
    worker.attach_channel(channel)
    await worker.start()
    try:
        gated = asyncio.create_task(
            worker.service_call(
                Frame(
                    id="call-alice",
                    method=CALL_METHOD,
                    path="/op/gated_user",
                    data={"identity": "alice", "kwargs": {}},
                )
            )
        )
        # The gated op is sync: it holds a pool thread, the loop stays free.
        while "alice" not in worker.user_items:
            await asyncio.sleep(0.01)
        await worker.service_call(
            Frame(
                id="call-bob",
                method=CALL_METHOD,
                path="/op/new_user",
                data={"identity": "bob", "kwargs": {}},
            )
        )
        worker.gate.set()
        await gated
    finally:
        await worker.shutdown()
    envelopes = {frame.id: [e["user"] for e in frame.data["events"]] for frame in channel.frames}
    assert envelopes == {"call-bob": ["bob"], "call-alice": ["alice"]}


async def test_a_call_parked_on_the_loop_does_not_make_the_worker_deaf(
    harness: WorkerHarness,
) -> None:
    """Serving is a task: the probe is answered while the first CALL is parked.

    The parked op is async, so it holds the loop's own coroutine and not a
    pool thread: were ``handle_frame`` to service inline, the receive loop
    would never read the probe's frame.
    """
    worker = harness.worker
    assert isinstance(worker, ProbeWorker)
    gated = asyncio.create_task(harness.call("/op/gated_async_user", {"identity": "alice"}))
    await asyncio.wait_for(worker.entered.wait(), timeout=5.0)
    report = await harness.call("/op/occupancy", {"identity": None, "kwargs": {}})
    assert report["users"] == 1
    assert gated.done() is False
    worker.async_gate.set()
    entry = await asyncio.wait_for(gated, timeout=5.0)
    assert entry["register_item_id"] == "alice"
    # The probe's REPLY landed first, and each envelope carries only its own events.
    assert harness.folded[0] == []
    assert [(e["op"], e["user"]) for e in harness.folded[1]] == [("new_user", "alice")]


async def test_the_http_call_form_answers_an_explicit_error_reply(
    harness: WorkerHarness,
) -> None:
    # the form reaches the seam only on a path that names no op: an op path
    # executes its op whatever its kwargs carry (the ops' **fields are open)
    with pytest.raises(ChannelCallError, match="phase B"):
        await harness.call("/sales/order", {"identity": "alice", "http": {"path": "/"}})
    assert "alice" not in harness.worker.user_items


async def test_an_unknown_op_answers_an_error_reply(harness: WorkerHarness) -> None:
    with pytest.raises(ChannelCallError, match="unknown op"):
        await harness.call("/op/store_lock", {"identity": "alice"})


async def test_a_failing_handler_answers_an_error_reply_with_the_pending_events(
    harness: WorkerHarness,
) -> None:
    await harness.call("/op/new_user", {"identity": "alice"})
    harness.folded.clear()
    with pytest.raises(ChannelCallError, match="handler exploded"):
        await harness.call("/op/boom", {"identity": "alice"})
    # The worker survives its handler and still serves the next CALL.
    assert await harness.call("/op/async_probe", {"identity": "alice"}) == {"identity": "alice"}


async def test_a_service_that_raises_past_the_reply_is_logged_and_the_worker_serves_on(
    caplog: Any,
) -> None:
    """The guard lives inside the task: a REPLY the dropped channel refuses —
    outside ``answer_call``'s own catch — is logged, never left unretrieved,
    and the worker still serves the next CALL."""
    worker = ProbeWorker("W:w1")
    channel = RecordingChannel()
    worker.attach_channel(channel)
    real_send = channel.send_frame
    dropped: list[str] = []

    async def flaky_wire(frame: Frame) -> str:
        if not dropped:
            dropped.append(frame.id)
            raise ConnectionError("not connected")
        return await real_send(frame)

    channel.send_frame = flaky_wire  # type: ignore[method-assign]
    try:
        with caplog.at_level("ERROR"):
            await worker.handle_frame(
                Frame(
                    id="call-1",
                    method=CALL_METHOD,
                    path="/op/new_user",
                    data={"identity": "alice", "kwargs": {}},
                )
            )
            await asyncio.gather(*list(worker._service_tasks))
        assert dropped == ["call-1"]
        assert "W:w1" in caplog.text
        assert "CALL /op/new_user" in caplog.text
        assert "ConnectionError" in caplog.text
        # The next CALL is serviced and its REPLY reaches the wire.
        await worker.handle_frame(
            Frame(
                id="call-2",
                method=CALL_METHOD,
                path="/op/async_probe",
                data={"identity": "bob", "kwargs": {}},
            )
        )
        await asyncio.gather(*list(worker._service_tasks))
    finally:
        await worker.shutdown()
    assert [frame.id for frame in channel.frames] == ["call-2"]
    assert channel.frames[0].data["result"] == {"identity": "bob"}


# ----------------------------------------------------------------------
# The async drain and the occupancy probe
# ----------------------------------------------------------------------


async def test_the_sender_task_still_ships_what_is_offered_to_the_outbox(
    harness: WorkerHarness,
) -> None:
    """Idle infrastructure, not dead: no 2a producer feeds it, the wiring holds."""
    await harness.worker.start()
    harness.worker.outbox.offer({"op": "new_user", "seq": 1, "user": "alice"})
    harness.worker.outbox.offer({"op": "drop_user", "seq": 2, "user": "alice"})
    await harness.wait_events(2)
    op_frames = [f for f in harness.events if f.path.startswith("/op/")]
    assert [f.path for f in op_frames] == ["/op/new_user", "/op/drop_user"]
    assert [f.data["seq"] for f in op_frames] == [1, 2]
    assert harness.worker.outbox.pending() == 0


async def test_the_occupancy_op_answers_what_the_registers_can_tell(
    harness: WorkerHarness,
) -> None:
    """Answered, never pushed: the probe CALLs and the loop produces the report."""
    await harness.call("/op/new_user", {"identity": "alice"})
    report = await harness.call("/op/occupancy", {"identity": None, "kwargs": {}})
    assert report["worker"] == "W:w1"
    assert report["users"] == 1
    assert report["pages"] == 0
    assert report["seq"] == 1
    # An op that shapes nothing: its own REPLY carries an empty envelope.
    assert harness.folded[-1] == []
    assert harness.events == []


async def test_shutdown_stops_the_tasks_and_closes_the_channel_without_orphan(
    harness: WorkerHarness,
) -> None:
    orphaned: list[Any] = []
    harness.channel.on_orphan = orphaned.append
    await harness.worker.start()
    await harness.worker.shutdown()
    await asyncio.wait_for(harness.channel.wait_closed(), timeout=5.0)
    assert orphaned == []
    assert harness.worker.pool.provisioned is False


def test_a_resident_login_links_the_connection_and_ships_nothing() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker) as events:
        worker.new_page("alice", "p1", session_id="sess-1")
        page_store = worker.page_items.get("p1")["store"]
        events.clear()
        worker.new_connection("sess-2")
        entry = worker.change_connection_user("sess-2", user="alice")
        # The worker already hosts alice: the registry's join is the whole
        # login, so the event goes up with no baggage to place.
        assert entry["register_item_id"] == "alice"
        assert [e["op"] for e in events] == [
            "new_user",
            "new_connection",
            "change_connection_user",
        ]
        assert events[-1]["session_id"] == "sess-2"
        assert events[-1]["previous_user"] == "sess-2"
        assert "package" not in events[-1]
    # Nothing was evicted: the resident entry, its first connection and its page
    # are the same live objects they were before the second one logged in.
    assert worker.user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    assert worker.page_items.get("p1")["store"] is page_store
    assert worker.connection_items.get("sess-1")["pages"] == {"p1"}
    # The orphaned guest died with its last connection.
    assert "sess-2" not in worker.user_items


def test_a_self_login_leaves_the_user_whole() -> None:
    # previous_user == user: the link branch re-adds the connection to the very
    # set it was discarded from, so the emptiness check that drops the previous
    # user must run AFTER the re-add — this test pins that order.
    worker = UserStickyWorker("W:w1")
    with call_sink(worker) as events:
        worker.new_page("alice", "p1", session_id="sess-1")
        entry = worker.user_items.get("alice")
        user_store, connections = entry["store"], entry["connections"]
        events.clear()
        worker.change_connection_user("sess-1", user="alice")
        assert [e["op"] for e in events] == ["change_connection_user"]
        assert events[-1]["previous_user"] == "alice"
        assert "package" not in events[-1]
    resident = worker.user_items.get("alice")
    assert resident is entry
    assert resident["store"] is user_store
    assert resident["connections"] is connections
    assert resident["connections"] == {"sess-1"}
    assert worker.connection_items.get("sess-1")["pages"] == {"p1"}
    assert worker.page_items.get("p1") is not None


def test_build_registry_is_the_worker_seam() -> None:
    """A worker subclass supplies its whole registry through one factory."""

    class SeamRegistry(RegisterRegistry):
        pass

    class SeamWorker(UserStickyWorker):
        def build_registry(self) -> RegisterRegistry:
            return SeamRegistry()

    assert isinstance(SeamWorker("W:w1").registry, SeamRegistry)
    assert isinstance(UserStickyWorker("W:w1").registry, RegisterRegistry)
