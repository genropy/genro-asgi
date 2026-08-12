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
import ctypes
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

import pytest
from genro_routes import route

from genro_asgi.channel import ChannelCallError, ChannelHub, Frame, LocalChannel
from genro_asgi.channel.hub import CALL_METHOD
from genro_asgi.spa import RegisterRegistry
from genro_asgi.spa.worker import (
    CONNECTION_MAX_AGE,
    EXCHANGE_OPS,
    GUEST_MAX_AGE,
    LIFECYCLE_OPS,
    PAGE_MAX_AGE,
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

    @route()
    def page_probe(self, identity: str, page_id: str) -> dict[str, Any]:
        """A page-addressed no-op: the REPLY's delivery is the thing under test."""
        return {"page": page_id}


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
        assert worker.connection_items.get("sess-1")["user"] == "guest_sess-1"

        entry = worker.change_connection_user("sess-1", user="alice", tenant="acme")
        # The login's own fields describe the real user, so they are on the entry
        # it creates — and the entry STAYS here: the anonymous item is transferred
        # onto the new key, and the event announces the re-label carrying nothing.
        assert entry["tenant"] == "acme"
        assert entry["register_item_id"] == "alice"
        assert "guest_sess-1" not in worker.user_items
        assert "alice" in worker.user_items
        assert "encoded" not in events[-1]

        worker.drop_user("alice")
        assert "alice" not in worker.user_items

        assert [(e["op"], e["seq"]) for e in events] == [
            ("new_user", 1),
            ("new_connection", 2),
            ("change_connection_user", 3),
            ("drop_user", 4),
        ]
        assert {e["worker"] for e in events} == {"W:w1"}
        assert events[2]["previous_user"] == "guest_sess-1"
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


def test_the_drop_connection_op_demolishes_the_whole_cascade_in_order() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker) as events:
        worker.new_page("sess-1", "p1", session_id="sess-1")
        worker.new_page("sess-1", "p2", session_id="sess-1")
        events.clear()
        dropped = worker.drop_connection("sess-1", "sess-1")
        # The logout's handle: pages first (in the edge SET's own order — the
        # contract orders the species, never the siblings), the connection,
        # the user it was the last connection of — every announcement on this
        # CALL's own sink.
        shaped = [(e["op"], e.get("session_id"), e.get("page_id")) for e in events]
        assert sorted(shaped[:2]) == [
            ("drop_page", None, "p1"),
            ("drop_page", None, "p2"),
        ]
        assert shaped[2:] == [
            ("drop_connection", "sess-1", None),
            ("drop_user", None, None),
        ]
        assert dropped["register_item_id"] == "sess-1"
    assert len(worker.connection_items) == 0
    assert len(worker.page_items) == 0
    assert len(worker.user_items) == 0


def test_the_drop_connection_op_spares_the_user_with_a_sibling_connection() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker) as events:
        worker.new_page("alice", "p1", session_id="sess-1")
        worker.new_page("alice", "p2", session_id="sess-2")
        events.clear()
        worker.drop_connection("alice", "sess-1")
        assert [(e["op"], e.get("session_id"), e.get("page_id")) for e in events] == [
            ("drop_page", None, "p1"),
            ("drop_connection", "sess-1", None),
        ]
    assert "alice" in worker.user_items
    assert "sess-2" in worker.connection_items
    assert "p2" in worker.page_items


def test_the_drop_connection_op_refuses_an_unknown_connection() -> None:
    worker = UserStickyWorker("W:w1")
    with call_sink(worker):
        with pytest.raises(KeyError):
            worker.drop_connection("alice", "sess-ghost")


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
    stamp = wired.pop("last_refresh_ts")
    assert wired == {"register_item_id": "sess-1", "user": "alice"}
    # The expiry stamp is a plain float: a scalar the wire carries like any other.
    assert isinstance(stamp, float)


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
        # The commanded eviction is the one road out and the install the road
        # back in: neither shapes an event, so the login is the last op heard.
        encoded = worker.evict_user("alice")["encoded"]
        worker.add_user("alice", encoded)
        assert [e["op"] for e in events] == [
            "new_user",
            "new_connection",
            "change_connection_user",
        ]
    assert worker.shape_event("add_user", user="alice") is None


# ----------------------------------------------------------------------
# The install primitives — the move round-trip preserves the entry
# ----------------------------------------------------------------------


def test_the_login_entry_survives_the_move_round_trip() -> None:
    """The login builds the entry HERE; only a commanded move carries it away."""
    source = UserStickyWorker("W:w1")
    target = UserStickyWorker("W:w2")
    with call_sink(source) as events:
        source.new_connection("sess-1")
        entry = source.change_connection_user(
            "sess-1", user="alice", tenant="acme", tags=["admin"]
        )
        # The login never ships: the re-labelled slice is still here and the
        # event that announced it carries no parcel at all.
        assert "alice" in source.user_items
        assert "encoded" not in events[-1]
        encoded = source.evict_user("alice")["encoded"]
    assert "alice" not in source.user_items

    installed = target.add_user("alice", encoded)
    assert installed["tenant"] == "acme"
    assert installed["tags"] == ["admin"]
    assert installed["register_item_id"] == "alice"
    # An op answers with the wire view — plus the caller's anomaly signal: an
    # install on an empty room never joined anybody.
    assert installed["joined"] is False
    assert {**target.wire_entry(target.user_items.get("alice")), "joined": False} == installed
    # The package is a deepcopy: the source's own entry never reached it.
    assert installed is not entry


def test_the_commanded_eviction_hands_the_slice_over_and_announces_nothing() -> None:
    """``evict_user`` answers with the parcel: the commander asked, so it is told."""
    source = UserStickyWorker("W:w1")
    target = UserStickyWorker("W:w2")
    with call_sink(source) as events:
        source.new_connection("sess-1", user="alice", tenant="acme")
        source.new_page("alice", page_id="p1", session_id="sess-1")
        source.page_items.get("p1")["store"]["counter"] = 1
        announced = len(events)
        result = source.evict_user("alice")
        # Operational: the reply IS the news, nothing rides an event.
        assert len(events) == announced
    assert "alice" not in source.user_items
    assert source.connection_items.get("sess-1") is None
    assert source.page_items.get("p1") is None

    installed = target.add_user("alice", result["encoded"])
    assert installed["register_item_id"] == "alice"
    arrived = target.connection_items.get("sess-1")
    assert (arrived["user"], arrived["tenant"]) == ("alice", "acme")
    assert target.page_items.get("p1")["store"]["counter"] == 1


def test_evicting_a_user_nobody_holds_is_an_error() -> None:
    worker = UserStickyWorker("W:w1")
    with pytest.raises(KeyError, match="unknown user"):
        worker.evict_user("ghost")


def test_add_user_refuses_a_package_addressed_to_another_identity() -> None:
    source = UserStickyWorker("W:w1")
    target = UserStickyWorker("W:w2")
    with call_sink(source):
        source.new_connection("sess-1")
        source.change_connection_user("sess-1", user="alice")
        encoded = source.evict_user("alice")["encoded"]
    with pytest.raises(ValueError, match="addressed to"):
        target.add_user("bob", encoded)


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
    with pytest.raises(ChannelCallError, match="hosts no WSGI site"):
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


async def test_the_report_carries_the_five_process_gauges(
    harness: WorkerHarness,
) -> None:
    """Raw sensor readings, no judgement: cpu, rss, reusable, trim_s, pressure."""
    report = harness.worker.occupancy_report()
    # First report: no previous probe to diff against.
    assert report["cpu"] is None
    assert report["rss"] is None or isinstance(report["rss"], int)
    assert report["reusable"] is None or isinstance(report["reusable"], int)
    assert report["trim_s"] is None or (
        isinstance(report["trim_s"], float) and report["trim_s"] >= 0.0
    )
    # Nothing sync dispatched yet — the pool is unprovisioned, so zeros.
    assert report["executor"] == {"busy": 0, "total": 0}


async def test_the_report_trims_the_heap_before_reading_the_rss(
    harness: WorkerHarness,
) -> None:
    """Order is the point: a trimmed heap is what makes the RSS reading honest."""
    calls: list[str] = []

    def record_trim() -> float:
        calls.append("trim")
        return 0.0

    def record_rss() -> int:
        calls.append("rss")
        return 4096

    harness.worker.trim_heap = record_trim  # type: ignore[method-assign]
    harness.worker.rss_bytes = record_rss  # type: ignore[method-assign]
    report = harness.worker.occupancy_report()
    assert calls == ["trim", "rss"]
    assert report["rss"] == 4096


async def test_the_report_carries_what_the_reusable_gauge_measured(
    harness: WorkerHarness,
) -> None:
    """The field is wired to the gauge, not hand-written: the sentinel travels."""
    harness.worker.reusable_bytes = lambda: 123456  # type: ignore[method-assign]
    assert harness.worker.occupancy_report()["reusable"] == 123456


async def test_the_report_carries_what_the_trim_measured(
    harness: WorkerHarness,
) -> None:
    """Same pin as reusable: trim_s is wired to the gauge, not hand-written."""
    harness.worker.trim_heap = lambda: 0.5  # type: ignore[method-assign]
    assert harness.worker.occupancy_report()["trim_s"] == 0.5


async def test_cpu_fraction_needs_two_probes_to_exist(
    harness: WorkerHarness,
) -> None:
    assert harness.worker.cpu_fraction() is None
    second = harness.worker.cpu_fraction()
    assert isinstance(second, float)
    assert second >= 0.0


async def test_rss_bytes_is_none_where_proc_is_absent(
    harness: WorkerHarness,
) -> None:
    """Platform-dependent by design: /proc-only, no psutil dependency."""
    rss = harness.worker.rss_bytes()
    assert rss is None or (isinstance(rss, int) and rss > 0)


async def test_the_heap_gauges_are_off_where_glibc_is_absent(
    harness: WorkerHarness,
) -> None:
    """The no-glibc path, forced: the handles are None, both gauges degrade."""
    harness.worker.libc_malloc_trim = None
    harness.worker.libc_mallinfo2 = None
    assert harness.worker.trim_heap() is None  # a silent no-op, never an error
    assert harness.worker.reusable_bytes() is None


def has_glibc_symbol(name: str) -> bool:
    """Whether the process C library exposes ``name``.

    False also where ``CDLL(None)`` itself fails — the same guard the
    worker's ``resolve_heap_symbols`` holds, so collection never breaks on a
    platform with no global libc handle.
    """
    try:
        return hasattr(ctypes.CDLL(None), name)
    except (OSError, TypeError):
        return False


@pytest.mark.skipif(
    not has_glibc_symbol("mallinfo2"),
    reason="mallinfo2 needs glibc >= 2.33",
)
async def test_reusable_bytes_reads_the_glibc_heap(
    harness: WorkerHarness,
) -> None:
    """Where glibc answers: free bytes held by the C heap, a plain count."""
    reusable = harness.worker.reusable_bytes()
    assert isinstance(reusable, int)
    assert reusable >= 0


@pytest.mark.skipif(
    not has_glibc_symbol("malloc_trim"),
    reason="malloc_trim needs glibc",
)
async def test_trim_heap_runs_where_glibc_answers(
    harness: WorkerHarness,
) -> None:
    """The trim is callable and answers its own duration — the cost reading."""
    duration = harness.worker.trim_heap()
    assert isinstance(duration, float)
    assert duration >= 0.0


async def test_the_executor_gauge_measures_the_sync_op_pool_only(
    harness: WorkerHarness,
) -> None:
    """``http_pool`` is the WSGI rail's and is never measured.

    Idle, the twin pools are indistinguishable — so each half holds ONE of
    them busy behind a gate while the report is read: the rail's burst must
    not reach the gauge, the op pool's must.
    """
    gate = threading.Event()
    holding = asyncio.create_task(harness.worker.http_pool.run(gate.wait))
    try:
        await asyncio.sleep(0)  # the task's first step runs run() up to the executor await
        assert harness.worker.http_pool.metrics["busy"] == 1
        assert harness.worker.occupancy_report()["executor"]["busy"] == 0
    finally:
        gate.set()  # ALWAYS released: a red assert must not wedge the pool thread
        await holding
    gate.clear()
    holding = asyncio.create_task(harness.worker.pool.run(gate.wait))
    try:
        await asyncio.sleep(0)
        assert harness.worker.pool.metrics["busy"] == 1
        assert harness.worker.occupancy_report()["executor"]["busy"] == 1
    finally:
        gate.set()
        await holding


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
        assert events[-1]["previous_user"] == "guest_sess-2"
        assert "encoded" not in events[-1]
    # Nothing was evicted: the resident entry, its first connection and its page
    # are the same live objects they were before the second one logged in.
    assert worker.user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    assert worker.page_items.get("p1")["store"] is page_store
    assert worker.connection_items.get("sess-1")["pages"] == {"p1"}
    # The orphaned guest died with its last connection.
    assert "guest_sess-2" not in worker.user_items


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
        assert "encoded" not in events[-1]
    resident = worker.user_items.get("alice")
    assert resident is entry
    assert resident["store"] is user_store
    assert resident["connections"] is connections
    assert resident["connections"] == {"sess-1"}
    assert worker.connection_items.get("sess-1")["pages"] == {"p1"}
    assert worker.page_items.get("p1") is not None


def test_the_drain_loses_nothing_to_a_concurrent_depositor() -> None:
    """A depositor thread and repeated drains: the union is the whole deposit.

    The depositor writes the way a pool thread does — under ``dispatch_lock``,
    a real store write plus a dbevent append — while the drain runs from
    another thread. Without the lock on ``collect_page`` the read-and-reset
    window can swallow a deposit landing inside it.
    """
    worker = UserStickyWorker("W:w1")
    worker.registry.new_page("p1", user="u1", session_id="s1")
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    store = worker.page_items.get("p1")["store"]
    deposits = 400
    drained_changes: list[dict[str, Any]] = []
    drained_events: list[dict[str, Any]] = []
    done = threading.Event()

    def depositor() -> None:
        for index in range(deposits):
            with worker.dispatch_lock:
                store[f"form.f{index}"] = index
                worker.deposit_dbevent("p1", {"table": "adm.user", "index": index})
        done.set()

    thread = threading.Thread(target=depositor)
    thread.start()
    try:
        while not done.is_set():
            collected = worker.collect_page("p1")
            drained_changes.extend(collected["datachanges"])
            drained_events.extend(collected["dbevents"])
    finally:
        thread.join(timeout=5.0)
    collected = worker.collect_page("p1")
    drained_changes.extend(collected["datachanges"])
    drained_events.extend(collected["dbevents"])
    assert [event["index"] for event in drained_events] == list(range(deposits))
    leaves = [
        change["key"]["path"]
        for change in drained_changes
        if change["key"]["path"] != "form"
    ]
    assert leaves == [f"form.f{index}" for index in range(deposits)]


async def test_a_page_evicted_between_the_call_and_its_reply_still_gets_a_reply(
    harness: Any,
) -> None:
    """The other half of B1: the existence check rides the pool trip, under the lock.

    ``send_reply`` hands the delivery drain to the pool, so between the CALL and
    its REPLY there is a thread handoff a concurrent eviction can win. The check
    lives inside ``wire_delivery``'s lock hold: a page gone by then yields an
    empty delivery and the REPLY still departs — before, the drain raised on the
    pool thread and the caller hung to timeout.
    """
    worker = harness.worker
    await harness.call(
        "/op/new_page",
        {"identity": "sess-1", "kwargs": {"page_id": "p1", "session_id": "sess-1"}},
    )
    original = worker.pool.run

    async def racing(fn: Any, *args: Any) -> Any:
        # The eviction wins the handoff: the page goes before the trip lands.
        if getattr(fn, "func", None) == worker.wire_delivery:
            with worker.dispatch_lock:
                worker.demolish_page("p1", worker.offer_lifecycle)
        return await original(fn, *args)

    worker.pool.run = racing  # type: ignore[method-assign]
    payload = await harness.hub.call(
        worker.name,
        "/op/page_probe",
        {"identity": "sess-1", "kwargs": {"page_id": "p1"}},
        timeout=5.0,
    )
    assert payload["result"] == {"page": "p1"}
    assert "datachanges" not in payload and "dbevents" not in payload
    assert worker.page_items.get("p1") is None


def test_build_registry_is_the_worker_seam() -> None:
    """A worker subclass supplies its whole registry through one factory."""

    class SeamRegistry(RegisterRegistry):
        pass

    class SeamWorker(UserStickyWorker):
        def build_registry(self) -> RegisterRegistry:
            return SeamRegistry()

    assert isinstance(SeamWorker("W:w1").registry, SeamRegistry)
    assert isinstance(UserStickyWorker("W:w1").registry, RegisterRegistry)


def caching_worker(*page_ids: str) -> UserStickyWorker:
    """A worker holding pages of one user, each caching ``adm.user`` in its store.

    The pages are born through the OP, which is what attaches the cache
    observer: a row created straight on the registry has no observer at all.
    """
    worker = UserStickyWorker("W:w1")
    with call_sink(worker):
        for page_id in page_ids:
            worker.new_page("u1", page_id, session_id="s1")
    for page_id in page_ids:
        store = worker.page_items.get(page_id)["store"]
        store.set_item("cache.users", "payload", _caching_table="adm.user")
    return worker


def test_a_caching_write_lands_in_the_table_cache_index() -> None:
    """Only the node naming a table is indexed, whatever the page subscribed."""
    worker = caching_worker("p1")
    store = worker.page_items.get("p1")["store"]
    store["plain.value"] = 1
    store.set_item("cache.roles", "payload", _caching_table="adm.role")
    assert worker.cached_tables == {
        "adm.user": {"p1": {"cache.users"}},
        "adm.role": {"p1": {"cache.roles"}},
    }


def test_a_dbevent_writes_none_over_every_cached_path() -> None:
    """The invalidation is a real store write, so a subscribed page drains it."""
    worker = caching_worker("p1")
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="cache")
    store = worker.page_items.get("p1")["store"]
    store.set_item("cache.roles", "role payload", _caching_table="adm.user")
    worker.collect_page("p1")
    worker.notifyDbEvents("u1", dbevents={"adm.user": [{"dbevent": "I"}]}, page_id="p1")
    assert store["cache.users"] is None
    assert store["cache.roles"] is None
    collected = worker.collect_page("p1")
    assert {change["key"]["path"] for change in collected["datachanges"]} == {
        "cache.users",
        "cache.roles",
    }
    # The node keeps its ``_caching_table``, so the None write is recorded in
    # turn: the entry now describes a cache holding None, exactly as it does in
    # the daemon after ``invalidateTableCache``.
    assert worker.cached_tables == {"adm.user": {"p1": {"cache.users", "cache.roles"}}}


def test_an_unsubscribed_page_is_invalidated_without_hearing_about_it() -> None:
    """The observer ignores the collector's filter; the delivery does not."""
    worker = caching_worker("p1")
    store = worker.page_items.get("p1")["store"]
    worker.notifyDbEvents("u1", dbevents={"adm.user": [{"dbevent": "I"}]}, page_id="p1")
    assert store["cache.users"] is None
    assert worker.collect_page("p1")["datachanges"] == []


def test_the_descending_dbevents_batch_invalidates_the_table_cache() -> None:
    """The other rail invalidates too, once for a table however many pages cached it."""
    worker = caching_worker("p1", "p2")
    deposit = {"table": "adm.user", "batch": [{"dbevent": "I"}], "ts": 1.0}
    worker.apply_dbevents_batch(
        [{"page_id": "p1", "deposit": deposit}, {"page_id": "p2", "deposit": deposit}]
    )
    assert worker.page_items.get("p1")["store"]["cache.users"] is None
    assert worker.page_items.get("p2")["store"]["cache.users"] is None
    assert worker.page_items.get("p1")["dbevents"] == [deposit]


def test_a_local_only_notify_invalidates_nothing() -> None:
    """The hidden transaction belongs to its page: no fan-out, no cache check."""
    worker = caching_worker("p1")
    store = worker.page_items.get("p1")["store"]
    worker.notifyDbEvents(
        "u1", dbevents={"adm.user": [{"dbevent": "I"}]}, page_id="p1", local_only=True
    )
    assert store["cache.users"] == "payload"
    assert worker.cached_tables == {"adm.user": {"p1": {"cache.users"}}}


def test_dropping_a_page_forgets_its_cached_paths() -> None:
    """The page leaves every table entry, and its store stops being watched."""
    worker = caching_worker("p1", "p2")
    departed = worker.page_items.get("p1")["store"]
    with call_sink(worker):
        worker.drop_page("u1", "p1")
    assert worker.cached_tables == {"adm.user": {"p2": {"cache.users"}}}
    departed.set_item("cache.roles", "payload", _caching_table="adm.user")
    assert worker.cached_tables == {"adm.user": {"p2": {"cache.users"}}}
    with call_sink(worker):
        worker.drop_page("u1", "p2")
    assert worker.cached_tables == {}


# ----------------------------------------------------------------------
# Expiry — the server-stamped refresh and the disarmed sweep
# ----------------------------------------------------------------------


def aged_worker(**kwargs: Any) -> UserStickyWorker:
    """A worker holding a logged-in page and a guest one, both born stamped.

    ``mario`` is a real user (its connection is named apart from it), while the
    guest connection's user carries the reserved ``guest_`` prefix — the name
    the consumer declares for an anonymous reception, which is what the guest
    rule reads.
    """
    worker = UserStickyWorker("W:w1", **kwargs)
    with call_sink(worker):
        worker.new_page("mario", "p1", session_id="s1")
        worker.new_page("guest_g1", "pg", session_id="g1")
    return worker


def age_page(worker: UserStickyWorker, page_id: str, seconds: float) -> None:
    """Push one page's stamp back in time, leaving the chain above it fresh."""
    worker.page_items.get(page_id)["last_refresh_ts"] -= seconds


def test_every_row_of_the_chain_is_born_stamped() -> None:
    """The stamp exists from birth: the sweep needs no fallback to a start time."""
    born = time.time()
    worker = aged_worker()
    stamps = [
        worker.page_items.get("p1")["last_refresh_ts"],
        worker.connection_items.get("s1")["last_refresh_ts"],
        worker.user_items.get("mario")["last_refresh_ts"],
    ]
    assert all(born <= stamp <= time.time() for stamp in stamps)


async def test_a_page_addressed_call_refreshes_the_whole_chain(harness: Any) -> None:
    """The page's own CALL is its sign of life, and it climbs to its user."""
    worker = harness.worker
    await harness.call(
        "/op/new_page", {"identity": "mario", "kwargs": {"page_id": "p1", "session_id": "s1"}}
    )
    rows = [
        worker.page_items.get("p1"),
        worker.connection_items.get("s1"),
        worker.user_items.get("mario"),
    ]
    for row in rows:
        row["last_refresh_ts"] = 0.0

    before = time.time()
    await harness.call(
        "/op/setStoreSubscription",
        {"identity": "mario", "kwargs": {"page_id": "p1", "storename": "page", "prefix": "gnr"}},
    )

    assert all(before <= row["last_refresh_ts"] <= time.time() for row in rows)


async def test_a_call_addressing_no_page_stamps_nothing(harness: Any) -> None:
    """Only a page-addressed CALL refreshes: a worker-level op is nobody's life sign."""
    worker = harness.worker
    with call_sink(worker):
        worker.new_page("mario", "p1", session_id="s1")
    worker.user_items.get("mario")["last_refresh_ts"] = 0.0

    await harness.call("/op/occupancy", {"identity": "mario"})

    assert worker.user_items.get("mario")["last_refresh_ts"] == 0.0


def test_a_fresh_chain_survives_the_sweep() -> None:
    """Nothing is dropped and nothing ascends while every stamp is recent."""
    worker = aged_worker()
    assert worker.sweep_expired() == {"pages": [], "connections": []}
    assert worker.outbox.pending() == 0


def test_an_aged_page_is_swept_with_its_cascade_on_the_outbox() -> None:
    """The out-of-request drop rides the outbox, cascade included, in climbing order."""
    worker = aged_worker()
    age_page(worker, "p1", PAGE_MAX_AGE + 1)

    assert worker.sweep_expired() == {"pages": ["p1"], "connections": []}

    assert "p1" not in worker.page_items
    assert "s1" not in worker.connection_items
    assert "mario" not in worker.user_items
    assert [event["op"] for event in worker.outbox.drain()] == [
        "drop_page",
        "drop_connection",
        "drop_user",
    ]


def test_a_guest_page_ages_at_the_guest_rate() -> None:
    """Forty seconds for a guest, ten minutes for a page whose user has a name."""
    worker = aged_worker()
    age_page(worker, "p1", GUEST_MAX_AGE + 1)
    age_page(worker, "pg", GUEST_MAX_AGE + 1)

    assert worker.sweep_expired()["pages"] == ["pg"]

    assert "p1" in worker.page_items


def test_an_idle_connection_takes_its_pages_and_its_user_with_it() -> None:
    """A connection expires on its own age even while its pages are fresh."""
    worker = aged_worker()
    worker.connection_items.get("s1")["last_refresh_ts"] -= CONNECTION_MAX_AGE + 1

    assert worker.sweep_expired() == {"pages": [], "connections": ["s1"]}

    assert "p1" not in worker.page_items
    assert "mario" not in worker.user_items
    assert [event["op"] for event in worker.outbox.drain()] == [
        "drop_page",
        "drop_connection",
        "drop_user",
    ]


def test_a_guest_connection_ages_at_the_guest_rate() -> None:
    """The guest rule reads the same on a connection as on a page."""
    worker = aged_worker()
    for connection_id in ("s1", "g1"):
        worker.connection_items.get(connection_id)["last_refresh_ts"] -= GUEST_MAX_AGE + 1

    assert worker.sweep_expired()["connections"] == ["g1"]

    assert "s1" in worker.connection_items


def test_the_expiry_ages_are_constructor_kwargs() -> None:
    """A consumer tunes the sweep per worker; the module values are the defaults.

    An age far under the module default sweeps a page the default would have
    kept — the sweep reads the instance, not the module.
    """
    worker = aged_worker(page_max_age=5, guest_max_age=3, connection_max_age=9)
    age_page(worker, "p1", 6)
    age_page(worker, "pg", 4)

    assert worker.sweep_expired()["pages"] == ["p1", "pg"]

    untouched = UserStickyWorker("W:w2")
    assert untouched.page_max_age == PAGE_MAX_AGE
    assert untouched.guest_max_age == GUEST_MAX_AGE
    assert untouched.connection_max_age == CONNECTION_MAX_AGE


async def test_the_sweep_is_disarmed_unless_an_interval_is_given() -> None:
    """No interval, no task: an unheard-of page must not be killed for its silence."""
    worker = aged_worker()
    age_page(worker, "p1", PAGE_MAX_AGE + 1)
    await worker.start()
    try:
        await asyncio.sleep(0.05)
        assert "p1" in worker.page_items
    finally:
        await worker.shutdown()


async def test_an_armed_worker_sweeps_on_its_own_interval() -> None:
    """Given an interval, the loop runs the sweep off the loop thread, by itself."""
    worker = aged_worker(sweep_interval=0.01)
    age_page(worker, "p1", PAGE_MAX_AGE + 1)
    await worker.start()
    try:
        deadline = asyncio.get_running_loop().time() + 5.0
        while "p1" in worker.page_items:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("the armed sweep never dropped the aged page")
            await asyncio.sleep(0.01)
    finally:
        await worker.shutdown()
