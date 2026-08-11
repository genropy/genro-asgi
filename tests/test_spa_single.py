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

"""The single role: one process, one worker, the whole 2a and 2b protocol.

``UserStickyCommander(workers=0, local_worker=True)`` holds its worker in this
very process, on a ``LocalChannel`` instead of a socket. Nothing else changes —
same REGISTER, same CALL/REPLY carrying the causal envelope of that call, same
occupancy probe, same fold — so these tests are the protocol's own collaudo: what they exercise is
byte-for-byte what a spawned child would exercise (design §3.5a).

The login belongs here too, and it is no shortcut: one road even when the only
worker is the one the user just left — evicted onto the event, installed back
from the package, released only once the room is ready (R1/R3).

The 2b surface holds here too, with the same wiring a spawned child has: the
live stores and their view collectors, the pull delivery on the REPLY, the
addressed write and its filtered broadcast, the dbevents species, the global
store with its lock — and a login move carrying every pending across.
"""

from __future__ import annotations

import asyncio
import os
import pickle
from typing import Any

import pytest
from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_routes import route
from genro_tytx import from_tytx, to_tytx

import genro_asgi.channel as channel_package
import genro_asgi.spa as spa_package
from genro_asgi.channel.hub import ChannelCallError
from genro_asgi.spa.commander import UserStickyCommander
from genro_asgi.spa.worker import UserStickyWorker

SETTLE_TIMEOUT = 5.0


async def until(predicate: Any, timeout: float = SETTLE_TIMEOUT) -> None:
    """Await a condition without blocking the loop."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise TimeoutError("condition never became true")
        await asyncio.sleep(0.01)


@pytest.fixture
async def single() -> Any:
    """A commander in the single role: no child, its own worker, no heartbeat.

    The hub owns its own socket directory: a ``tmp_path`` under the pytest root
    overflows the ``AF_UNIX`` path limit.
    """
    commander = UserStickyCommander(
        workers=0,
        local_worker=True,
    )
    await commander.start()
    try:
        yield commander
    finally:
        await commander.stop()


# ----------------------------------------------------------------------
# The wiring: one member, in this process, and it is the reception
# ----------------------------------------------------------------------


async def test_the_local_worker_registers_like_any_child(single: UserStickyCommander) -> None:
    name = single.worker.name
    assert single.active_workers == [name]
    assert single.hub.resolve(name).pid == os.getpid()
    assert single.worker_roster[name]["process"] is None


async def test_the_reception_is_the_local_worker(single: UserStickyCommander) -> None:
    assert single.reception == single.worker.name
    assert single.worker_for("nobody-knows-me") == single.worker.name


async def test_no_child_is_spawned(single: UserStickyCommander) -> None:
    single.reconcile()
    assert single.target == 0
    assert single.living_workers == [single.worker.name]


# ----------------------------------------------------------------------
# The whole envelope round trip, over the queue wire
# ----------------------------------------------------------------------


async def test_a_lifecycle_call_folds_its_events_before_the_reply_is_released(
    single: UserStickyCommander,
) -> None:
    entry = await single.forward_call("sess-1", "/op/new_user")
    assert entry["register_item_id"] == "sess-1"
    # The fold ran inside the hub's REPLY handling: the surface is already current.
    assert single.user_worker_map == {"sess-1": single.worker.name}
    assert single.users_on(single.worker.name) == {"sess-1"}


async def test_every_frame_crosses_the_codec(single: UserStickyCommander) -> None:
    entry = await single.forward_call("sess-1", "/op/new_user", {"lang": "it"})
    stored = single.worker.user_items.get("sess-1")
    # An op answers with the wire view: the live store stays on the worker.
    assert entry == single.worker.wire_entry(stored)
    # Decoded from bytes, never a shared reference to the worker's own item.
    assert entry is not stored


async def test_an_unknown_op_comes_back_as_an_error_reply(
    single: UserStickyCommander,
) -> None:
    with pytest.raises(ChannelCallError, match="unknown op"):
        await single.forward_call("sess-1", "/op/no_such_op")


async def test_a_drop_rides_the_reply_of_the_call_that_caused_it(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_user")
    await single.forward_call("sess-1", "/op/drop_user")
    # The envelope is causal: the fold ran before the caller was resolved, so
    # the surface is already current when the drop returns.
    assert single.user_worker_map == {}
    assert single.users_on(single.worker.name) == set()


def spy_on_replies(commander: UserStickyCommander) -> list[tuple[str, list[dict[str, Any]]]]:
    """Record the path and the envelope of every REPLY the hub reads back.

    The payload reaches the caller verbatim from the frame, so this is what
    crossed the wire: one entry per CALL, in the order the hub resolved them.
    """
    seen: list[tuple[str, list[dict[str, Any]]]] = []
    original = commander.hub.call

    async def spying(name: str, path: str, data: Any = None, timeout: float | None = None) -> Any:
        payload = await original(name, path, data, timeout=timeout)
        seen.append((path, payload.get("events", [])))
        return payload

    commander.hub.call = spying
    return seen


async def test_every_reply_carries_only_the_events_of_its_own_call(
    single: UserStickyCommander,
) -> None:
    seen = spy_on_replies(single)
    await single.forward_call("sess-1", "/op/new_connection")
    await single.forward_call("sess-2", "/op/new_connection")
    await single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await single.probe_worker(single.worker.name)
    # Causal attribution: the lifecycle a call produced rides that call's REPLY —
    # never a neighbour's, and never an operational op's empty envelope.
    assert [(path, [event["op"] for event in events]) for path, events in seen] == [
        ("/op/new_connection", ["new_user", "new_connection"]),
        ("/op/new_connection", ["new_user", "new_connection"]),
        ("/op/change_connection_user", ["change_connection_user"]),
        ("/op/install_package", []),
        ("/op/occupancy", []),
    ]
    assert [event["user"] for _, events in seen for event in events] == [
        "sess-1",
        "sess-1",
        "sess-2",
        "sess-2",
        "alice",
    ]


async def test_the_occupancy_probe_is_answered_over_the_queue_wire(
    single: UserStickyCommander,
) -> None:
    name = single.worker.name
    await single.probe_worker(name)
    window = single.worker_roster[name]["occupancy"]
    assert window[-1]["report"]["worker"] == name


# ----------------------------------------------------------------------
# The login: one road even when the destination is the worker it left
# ----------------------------------------------------------------------


def gate_the_install(commander: UserStickyCommander, gate: asyncio.Event) -> dict[str, Any]:
    """Hold every install CALL on ``gate`` and record what the worker held then.

    The install is the middle of the ratified sequence, so parking there is the
    only way to observe the window in which the user exists nowhere but in the
    package riding the event.
    """
    seen: dict[str, Any] = {}
    original = commander.hub.call

    async def gated(name: str, path: str, data: Any = None, timeout: float | None = None) -> Any:
        if path.endswith("install_package"):
            seen["identity"] = data["identity"]
            seen["held"] = commander.worker.user_items.get(data["identity"])
            seen["flag"] = commander.user_worker_map.get(data["identity"], "missing")
            await gate.wait()
        return await original(name, path, data, timeout=timeout)

    commander.hub.call = gated
    return seen


async def test_a_login_evicts_the_slice_and_installs_it_back(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_connection")
    before = single.worker.user_items.get("sess-1")
    entry = await single.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "lang": "it"}
    )
    installed = single.worker.user_items.get("alice")
    assert entry["register_item_id"] == "alice"
    # The guest entry left with its last connection; the real user is its own.
    assert single.worker.user_items.get("sess-1") is None
    assert installed is not before
    assert installed["register_item_id"] == "alice"
    assert installed["lang"] == "it"
    assert single.user_worker_map == {"alice": single.worker.name}
    assert single.users_on(single.worker.name) == {"alice"}


async def test_the_login_is_released_only_once_the_room_is_ready(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_connection")
    gate = asyncio.Event()
    seen = gate_the_install(single, gate)
    login = asyncio.create_task(
        single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    )
    await until(lambda: "held" in seen)
    # Mid-sequence: the source spent its copy, the map carries the flag, and the
    # login caller is still parked on the install.
    assert seen["identity"] == "alice"
    assert seen["held"] is None
    assert seen["flag"] is None
    assert not login.done()
    gate.set()
    entry = await login
    assert entry["register_item_id"] == "alice"
    assert single.worker.user_items.get("alice") is not None


async def test_a_call_parked_on_the_flag_lands_after_the_placement(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_connection")
    gate = asyncio.Event()
    seen = gate_the_install(single, gate)
    login = asyncio.create_task(
        single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    )
    await until(lambda: "held" in seen)
    parked = asyncio.create_task(single.forward_call("alice", "/op/drop_user"))
    await asyncio.sleep(0.05)
    assert not parked.done()
    gate.set()
    await login
    dropped = await parked
    assert dropped["register_item_id"] == "alice"
    assert single.user_worker_map == {}


async def test_an_install_that_fails_leaves_the_user_nowhere(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_connection")
    original = single.hub.call

    async def failing(name: str, path: str, data: Any = None, timeout: float | None = None) -> Any:
        if path.endswith("install_package"):
            raise RuntimeError("no room")
        return await original(name, path, data, timeout=timeout)

    single.hub.call = failing
    with pytest.raises(RuntimeError, match="no room"):
        await single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert single.user_worker_map == {}
    assert single.worker.user_items.get("alice") is None
    # Nobody holds the user, so the next call for it is a guest arriving.
    single.hub.call = original
    assert single.worker_for("alice") == single.reception


async def test_the_user_stays_reachable_after_the_login(single: UserStickyCommander) -> None:
    await single.forward_call("sess-1", "/op/new_connection")
    await single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert single.worker_for("alice") == single.worker.name
    dropped = await single.forward_call("alice", "/op/drop_user")
    assert dropped["register_item_id"] == "alice"
    assert single.user_worker_map == {}


# ----------------------------------------------------------------------
# The 2b surface: the same flows a pool runs, with one worker in this process
# ----------------------------------------------------------------------


class PageWorker(UserStickyWorker):
    """The applicative worker a 2b flow needs: page-addressed ops and store writes.

    Nothing here is protocol — these are the three things an application does
    (call for a page, subscribe its view, write the user store), so the tests
    below reach the 2b machinery the way a real mount would.
    """

    @route()
    def page_ping(self, identity: str, page_id: str) -> dict[str, Any]:
        """The ordinary applicative CALL: it addresses a page, so it pulls its drain."""
        return {"identity": identity, "page_id": page_id}

    @route()
    def subscribe_prefix(self, identity: str, page_id: str, prefix: str) -> dict[str, Any]:
        """Widen the calling page's view of its user store — the Q-A subscription."""
        with self.dispatch_lock:
            self.registry.subscribe_store_path(page_id, prefix)
        return {"page_id": page_id, "prefix": prefix}

    @route()
    def write_user_store(self, identity: str, path: str, value: Any) -> dict[str, Any]:
        """Write the user's own store: the write IS the API, no smear loop."""
        with self.dispatch_lock:
            self.user_items.get(identity)["store"][path] = value
        return {"path": path}


@pytest.fixture
async def pages() -> Any:
    """The single role holding a ``PageWorker``: the whole 2b surface in one process."""
    commander = UserStickyCommander(
        workers=0,
        local_worker=True,
        worker_class=f"{__name__}:PageWorker",
    )
    await commander.start()
    try:
        yield commander
    finally:
        await commander.stop()


def delivered(envelope: dict[str, Any], key: str) -> Any:
    """Hydrate one delivery key the way the client side will."""
    return from_tytx(envelope[key], "json")


def a_change(path: str, value: Any) -> dict[str, Any]:
    """One real change dict, born from a real write on a throwaway Bag."""
    bag = Bag()
    collector = DataChangeCollector(bag)
    bag.set_item(path, value)
    return collector.drain()[-1]


def spy_on_posts(commander: UserStickyCommander) -> list[tuple[str, str]]:
    """Record every descending EVENT the commander pushes down the internal rail."""
    seen: list[tuple[str, str]] = []
    original = commander.hub.post

    async def spying(name: str, path: str, data: Any = None) -> str:
        seen.append((name, path))
        return await original(name, path, data)

    commander.hub.post = spying  # type: ignore[method-assign]
    return seen


async def make_page(commander: UserStickyCommander, user: str, page_id: str) -> None:
    """Bring a page of ``user`` into being through the ordinary lifecycle op.

    One connection per user here — the session id IS the sticky key, exactly as
    it is in the reception, so a guest's pages hang from the connection its
    login will re-label.
    """
    await commander.forward_call(user, "/op/new_page", {"page_id": page_id, "session_id": user})


async def pull(commander: UserStickyCommander, user: str, page_id: str) -> dict[str, Any]:
    """One page's own request/response cycle: the CALL that drains it."""
    return await commander.forward_envelope(user, "/op/page_ping", {"page_id": page_id})


async def test_a_user_store_write_lands_on_the_subscribed_pages_reply(
    pages: UserStickyCommander,
) -> None:
    await make_page(pages, "alice", "p1")
    await make_page(pages, "alice", "p2")
    await pages.forward_call("alice", "/op/subscribe_prefix", {"page_id": "p1", "prefix": "prefs"})

    await pages.forward_call("alice", "/op/write_user_store", {"path": "prefs.lang", "value": "it"})

    # The view collector of the subscriber found the write; the write itself was
    # one Bag mutation, with no smear loop anywhere.
    changes = delivered(await pull(pages, "alice", "p1"), "datachanges")
    assert [change["key"]["path"] for change in changes] == ["prefs", "prefs.lang"]
    assert changes[-1]["value"] == "it"
    assert delivered(await pull(pages, "alice", "p2"), "datachanges") == []


async def test_a_cross_page_signal_stays_inside_the_process(
    pages: UserStickyCommander,
) -> None:
    await make_page(pages, "alice", "p1")
    await make_page(pages, "alice", "p2")
    posts = spy_on_posts(pages)

    await pages.forward_call(
        "alice",
        "/op/set_datachange",
        {"change": to_tytx(a_change("gnr.x", 42), "json"), "kind": "page", "target": "p2"},
    )

    # Tier 2: the target sits on the producer's own worker, so the message never
    # reached the rail — and it landed as a deposit, not as a Bag write.
    assert posts == []
    changes = delivered(await pull(pages, "alice", "p2"), "datachanges")
    assert [(change["key"]["path"], change["value"]) for change in changes] == [("gnr.x", 42)]
    assert pages.worker.page_items.get("p2")["store"]["gnr.x"] is None


async def test_a_filtered_broadcast_reaches_exactly_the_pages_it_names(
    pages: UserStickyCommander,
) -> None:
    await make_page(pages, "alice", "p1")
    await make_page(pages, "bob", "p2")
    mine = pages.worker.page_items.get("p1")

    await pages.forward_call(
        "alice",
        "/op/set_datachange",
        {"change": to_tytx(a_change("gnr.x", 42), "json"), "filters": "user:alice"},
    )

    # A filtered address always ascends: the commander alone knows every page.
    await until(lambda: mine["collector"].pending == 1)
    changes = delivered(await pull(pages, "alice", "p1"), "datachanges")
    assert [change["key"]["path"] for change in changes] == ["gnr.x"]
    assert delivered(await pull(pages, "bob", "p2"), "datachanges") == []


async def test_a_dbevent_is_subscribed_notified_and_collected(
    pages: UserStickyCommander,
) -> None:
    await make_page(pages, "alice", "p1")
    await make_page(pages, "alice", "p2")
    await pages.forward_call(
        "alice", "/op/subscribeTable", {"page_id": "p1", "table": "sys.user"}
    )

    await pages.forward_call(
        "alice",
        "/op/notifyDbEvents",
        {"dbevents": {"sys.user": ["ins:1"]}, "reason": "commit", "page_id": "p2"},
    )

    deposits = delivered(await pull(pages, "alice", "p1"), "dbevents")
    assert [(d["table"], d["batch"], d["from_page_id"], d["reason"]) for d in deposits] == [
        ("sys.user", ["ins:1"], "p2", "commit")
    ]
    # Its own species: the subscriber's datachanges are untouched, and the
    # notifying page is not a subscriber.
    assert delivered(await pull(pages, "alice", "p1"), "dbevents") == []
    assert delivered(await pull(pages, "alice", "p2"), "dbevents") == []


async def test_a_global_store_write_reaches_the_only_replica(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_user")

    assert await single.forward_call(
        "sess-1", "/op/store_set", {"path": "gnr.a", "value": 1}
    ) == {"path": "gnr.a"}

    # Nothing is written locally: the replica is updated by the ordinary push.
    await until(lambda: single.worker.global_store["gnr.a"] == 1)
    assert single.global_master.bag["gnr.a"] == 1


async def test_the_global_store_lock_round_trips_in_one_process(
    single: UserStickyCommander,
) -> None:
    worker = single.worker

    async with worker.global_store_lock() as copy:
        copy.set_item("gnr.a", 1)
        # The master is untouched while the hold lasts: all-or-nothing.
        assert single.global_master.bag["gnr.a"] is None

    # The release ascends on the outbox, so the master is applied there and the
    # propagation comes back down: one order, the author's replica included.
    await until(lambda: single.global_master.bag["gnr.a"] == 1)
    await until(lambda: worker.global_store["gnr.a"] == 1)


async def test_a_login_move_carries_the_pending_delivery(
    pages: UserStickyCommander,
) -> None:
    await make_page(pages, "sess-1", "p1")
    await pages.forward_call("sess-1", "/op/subscribe_prefix", {"page_id": "p1", "prefix": "prefs"})
    # The subscriptions are taken FIRST: their CALLs address the page, so their
    # own REPLY would drain what the move is supposed to carry.
    await pages.forward_call(
        "sess-1", "/op/subscribeTable", {"page_id": "p1", "table": "sys.user"}
    )
    await pages.forward_call(
        "sess-1", "/op/write_user_store", {"path": "prefs.lang", "value": "it"}
    )

    entry = await pages.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})

    assert entry["register_item_id"] == "alice"
    # The page was reborn under the new key with its pendings and its
    # subscriptions: what it drains at destination is what it never read.
    changes = delivered(await pull(pages, "alice", "p1"), "datachanges")
    assert [change["key"]["path"] for change in changes] == ["prefs", "prefs.lang"]
    # The index the move rebuilt is the one the destination's fan-out reads: the
    # moved page notifies its own subscribed table and is served on that REPLY.
    envelope = await pages.forward_envelope(
        "alice", "/op/notifyDbEvents", {"dbevents": {"sys.user": ["ins:1"]}, "page_id": "p1"}
    )
    assert [(d["table"], d["batch"]) for d in delivered(envelope, "dbevents")] == [
        ("sys.user", ["ins:1"])
    ]


# ----------------------------------------------------------------------
# The login as a mutation: S1 and S2 with one worker in this process
# ----------------------------------------------------------------------


async def test_a_login_relabels_the_page_and_never_re_keys_it(
    pages: UserStickyCommander,
) -> None:
    await make_page(pages, "sess-1", "p1")

    await pages.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})

    # S1: the keys are untouched on both sides of the chain — the page kept its
    # id under the connection it was born on, and only the labels moved.
    page = pages.worker.page_items.get("p1")
    assert (page["connection_id"], pages.worker.registry.user_of_page("p1")) == (
        "sess-1",
        "alice",
    )
    assert pages.worker.connection_items.get("sess-1")["user"] == "alice"
    assert pages.connection_user[pages.page_connection["p1"]] == "alice"
    # And the surface edge survived, so the filtered broadcast finds it.
    await pages.forward_call(
        "alice",
        "/op/set_datachange",
        {"change": to_tytx(a_change("gnr.x", 42), "json"), "filters": "user:alice"},
    )
    await until(lambda: page["collector"].pending == 1)
    changes = delivered(await pull(pages, "alice", "p1"), "datachanges")
    assert [(change["key"]["path"], change["value"]) for change in changes] == [("gnr.x", 42)]


async def test_a_second_connection_of_the_same_user_joins_at_home(
    pages: UserStickyCommander,
) -> None:
    await make_page(pages, "sess-1", "p1")
    await pages.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await pages.forward_call(
        "alice", "/op/write_user_store", {"path": "prefs.theme", "value": "dark"}
    )

    # S2: the second guest logging in as an already-known user used to raise.
    await make_page(pages, "sess-2", "p2")
    await pages.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})

    assert pages.worker.user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    assert {pages.worker.registry.user_of_page(p) for p in ("p1", "p2")} == {"alice"}
    assert pages.user_worker_map == {"alice": pages.worker.name}
    # The resident store was joined, not replaced: what the first connection
    # wrote is still there for the second one to subscribe to.
    await pages.forward_call("alice", "/op/subscribe_prefix", {"page_id": "p2", "prefix": "prefs"})
    await pull(pages, "alice", "p2")
    await pages.forward_call(
        "alice", "/op/write_user_store", {"path": "prefs.lang", "value": "it"}
    )
    changes = delivered(await pull(pages, "alice", "p2"), "datachanges")
    assert [change["key"]["path"] for change in changes] == ["prefs.lang"]
    # Both connections' pages are served by one filtered broadcast.
    await pages.forward_call(
        "alice",
        "/op/set_datachange",
        {"change": to_tytx(a_change("gnr.x", 42), "json"), "filters": "user:alice"},
    )
    for page_id in ("p1", "p2"):
        page = pages.worker.page_items.get(page_id)
        await until(lambda page=page: page["collector"].pending == 1)
        changes = delivered(await pull(pages, "alice", page_id), "datachanges")
        assert [change["key"]["path"] for change in changes] == ["gnr.x"]


async def test_the_second_login_of_a_user_leaves_the_first_page_untouched(
    pages: UserStickyCommander,
) -> None:
    await make_page(pages, "sess-1", "p1")
    await pages.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    pages.worker.setStoreSubscription(
        "alice", page_id="p1", storename="page", prefix="counter"
    )
    page_row = pages.worker.page_items.get("p1")
    page_store = page_row["store"]
    page_store["counter"] = 1
    await make_page(pages, "sess-2", "p2")

    # The everyday case of the single role: EVERY second login of a user used to
    # evict the whole slice and put it back down, and p1's traffic fell into the
    # window. Now the login only links — the REPLY carries no package at all.
    seen = spy_on_replies(pages)
    await pages.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    logins = [
        event
        for _, events in seen
        for event in events
        if event["op"] == "change_connection_user"
    ]
    assert [("package" in event) for event in logins] == [False]
    assert [path for path, _ in seen] == ["/op/change_connection_user"]

    # p1 is the same row on the same Bag, and what was pending on it is still
    # there to be drained.
    assert pages.worker.page_items.get("p1") is page_row
    assert pages.worker.page_items.get("p1")["store"] is page_store
    assert pages.user_worker_map == {"alice": pages.worker.name}
    changes = delivered(await pull(pages, "alice", "p1"), "datachanges")
    assert [change["key"]["path"] for change in changes] == ["counter"]
    await pull(pages, "alice", "p2")


# ----------------------------------------------------------------------
# The public faces, after the pruning
# ----------------------------------------------------------------------


def test_the_packages_export_no_pruned_name() -> None:
    pruned = {
        "PendingMove",
        "MOVE_TIMEOUT",
        "MOVE_QUIESCE_TIMEOUT",
        "OPEN_REQUEST_TTL",
        "CALL_TIMEOUT",
        "MOVE_INSTALL_TIMEOUT",
        "OCCUPANCY_PATH",
        "OCCUPANCY_INTERVAL",
        "spawn_placements",
        "throttle_crash",
    }
    assert pruned.isdisjoint(spa_package.__all__)
    assert pruned.isdisjoint(channel_package.__all__)
    assert all(hasattr(spa_package, name) for name in spa_package.__all__)
    assert all(hasattr(channel_package, name) for name in channel_package.__all__)


# ----------------------------------------------------------------------
# Shutdown
# ----------------------------------------------------------------------


async def test_stopping_the_commander_takes_the_local_worker_down() -> None:
    commander = UserStickyCommander(workers=0, local_worker=True)
    await commander.start()
    worker = commander.worker
    channel = commander.local_channel
    await commander.stop()
    assert commander.worker is None
    assert not channel.connected
    assert worker.channel is channel
    assert commander.hub.members == {}


# ----------------------------------------------------------------------
# The total restart: the register crosses it as a move toward a file
# ----------------------------------------------------------------------


def restart_commander(dump: Any) -> UserStickyCommander:
    """A single-role commander armed with ``dump``."""
    return UserStickyCommander(
        workers=0,
        local_worker=True,
        dump_path=str(dump),
    )


async def test_the_register_crosses_a_total_restart_through_the_dump(tmp_path: Any) -> None:
    dump = tmp_path / "register.pik"
    first = restart_commander(dump)
    await first.start()
    await first.forward_call("sess-1", "/op/new_connection")
    await first.forward_call(
        "sess-1", "/op/new_page", {"page_id": "p1", "session_id": "sess-1"}
    )
    await first.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await first.forward_call(
        "sess-1", "/op/subscribeTable", {"table": "mytable", "page_id": "p1"}
    )
    first.worker.user_items.get("alice")["store"]["prefs.theme"] = "dark"
    await first.stop()
    assert dump.exists()
    # The dump is a departure like any other: the surface forgot its users.
    assert first.user_worker_map == {}
    # A dump left over by an older run is what the rename must overwrite.
    (tmp_path / "register_loaded.pik").write_bytes(b"stale")

    second = restart_commander(dump)
    await second.start()
    try:
        assert second.user_worker_map["alice"] == second.worker.name
        assert second.worker.user_items.get("alice")["store"]["prefs.theme"] == "dark"
        assert second.worker.connection_items.get("sess-1")["user"] == "alice"
        assert second.worker.page_items.get("p1")["session_id"] == "sess-1"
        # The surface is re-hung from the package itself (adopt_slice): the
        # operational install sends no events, so the fold never runs here.
        assert second.connection_user == {"sess-1": "alice"}
        assert second.worker_of_page("p1") == second.worker.name
        assert second.page_subscriptions.pages_for("mytable") == {"p1"}
        # The file is retired the moment it is read: a restart dying mid-restore
        # must not find it again and install everything twice.
        assert not dump.exists()
        assert (tmp_path / "register_loaded.pik").read_bytes() != b"stale"
    finally:
        await second.stop()


async def test_the_dump_leaves_behind_a_user_whose_evict_fails(tmp_path: Any) -> None:
    """Best-effort, pinned: a refused evict is logged and skipped, the rest is written."""
    dump = tmp_path / "register.pik"
    first = restart_commander(dump)
    await first.start()
    await first.forward_call("sess-1", "/op/new_connection")
    await first.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await first.forward_call("sess-2", "/op/new_connection")
    await first.forward_call("sess-2", "/op/change_connection_user", {"user": "bob"})
    original = first.forward_call

    async def refusing(
        identity: str, path: str, kwargs: Any = None, timeout: Any = None
    ) -> Any:
        if identity == "alice" and path.endswith("evict_user"):
            raise RuntimeError("the worker went away mid-shutdown")
        return await original(identity, path, kwargs, timeout)

    first.forward_call = refusing  # type: ignore[method-assign]
    await first.stop()
    packages = pickle.loads(dump.read_bytes())
    assert set(packages) == {"bob"}


async def test_the_restore_skips_a_package_it_cannot_install(tmp_path: Any) -> None:
    """Best-effort, pinned: a refused install is logged, skipped and unmapped."""
    dump = tmp_path / "register.pik"
    first = restart_commander(dump)
    await first.start()
    await first.forward_call("sess-2", "/op/new_connection")
    await first.forward_call("sess-2", "/op/change_connection_user", {"user": "bob"})
    await first.stop()
    packages = pickle.loads(dump.read_bytes())
    packages["alice"] = "not a package"
    dump.write_bytes(pickle.dumps(packages))

    second = restart_commander(dump)
    await second.start()
    try:
        assert "alice" not in second.user_worker_map
        assert second.user_worker_map["bob"] == second.worker.name
        assert second.worker.user_items.get("bob") is not None
    finally:
        await second.stop()


async def test_an_unarmed_commander_dumps_nothing(tmp_path: Any) -> None:
    commander = UserStickyCommander(workers=0, local_worker=True)
    await commander.start()
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await commander.stop()
    assert list(tmp_path.glob("*.pik")) == []
