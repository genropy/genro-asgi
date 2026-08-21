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

"""The addressed write: three tiers, the state/signal split, filtered broadcast.

The pool is real but in-process — two ``UserStickyWorker`` on the commander's own
hub over ``LocalChannel`` pairs — so an ascending message really rides the
outbox, is really resolved on the surface and really comes back down a
``/datachange_in`` EVENT. What the tests pin down is the switch: a target on the
producer's own worker costs no channel traffic at all, a target elsewhere lands
as a Bag write (state) or as a deposit (signal), a filtered address reaches
exactly the pages it names with ONE send per destination worker, and a target the
surface cannot resolve is dropped.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import pytest
from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_tytx import from_tytx, to_tytx

from genro_asgi.channel import ChannelCallError
from genro_asgi.channel.local import LocalChannel
from genro_asgi.spa.commander import UserStickyCommander
from genro_asgi.spa.worker import PAGE_MAX_AGE, UserStickyWorker

SETTLE_TIMEOUT = 5.0


async def until(predicate: Any, timeout: float = SETTLE_TIMEOUT) -> None:
    """Await a condition without blocking the loop."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise TimeoutError("condition never became true")
        await asyncio.sleep(0.01)


def a_change(path: str = "gnr.x", value: Any = 42) -> dict[str, Any]:
    """One real change dict, born from a real write on a throwaway Bag."""
    bag = Bag()
    collector = DataChangeCollector(bag)
    bag.set_item(path, value)
    return collector.drain()[-1]


def parcel(change: dict[str, Any]) -> Any:
    """The wire form of a change: the TYTX parcel the commander never opens."""
    return to_tytx(change, "json")


def wire_ts(change: dict[str, Any]) -> Any:
    """The producer's instant as it survives the wire.

    TYTX carries a datetime at millisecond precision, so the value a destination
    reads is the producer's, truncated by the vehicle — never restamped. That
    truncation is what these assertions compare against.
    """
    return from_tytx(parcel(change), "json")["change_ts"]


class Routed:
    """A commander with two in-process workers and every descending send recorded.

    The workers are wired exactly like spawned ones (a roster row with
    ``process=None``, a REGISTER over the channel, the same fold). ``sends``
    records what the commander pushes down the internal rail, which is how the
    batching is asserted.
    """

    def __init__(self) -> None:
        self.commander = UserStickyCommander(workers=0)
        self.workers: dict[str, UserStickyWorker] = {}
        self.sends: list[tuple[str, str, Any]] = []
        # The two ascending rails, told apart: what a REPLY's task class handed
        # to the commander, and what a worker's outbox took.
        self.commands: list[dict[str, Any]] = []
        self.ascended: list[dict[str, Any]] = []

    async def start(self, count: int = 2) -> None:
        await self.commander.start()
        hub_post = self.commander.hub.post
        spawn_command = self.commander.spawn_command

        async def recording_post(name: str, path: str, data: Any = None) -> str:
            self.sends.append((name, path, data))
            return await hub_post(name, path, data)

        def recording_spawn(worker: str, message: dict[str, Any]) -> Any:
            self.commands.append(message)
            return spawn_command(worker, message)

        self.commander.hub.post = recording_post  # type: ignore[method-assign]
        self.commander.spawn_command = recording_spawn  # type: ignore[method-assign]
        for _ in range(count):
            await self.add_worker()

    async def add_worker(self) -> str:
        commander = self.commander
        name = commander.next_worker_name()
        commander.worker_roster[name] = commander.new_roster_row(os.getpid(), None)
        worker = UserStickyWorker(name)
        offer = worker.outbox.offer

        def recording_offer(event: dict[str, Any]) -> None:
            self.ascended.append(event)
            offer(event)

        worker.outbox.offer = recording_offer  # type: ignore[method-assign]
        channel = LocalChannel(name)
        worker.attach_channel(channel)
        await channel.connect()
        await commander.hub.attach_local(channel)
        await worker.start()
        self.workers[name] = worker
        # A REGISTER seeds that worker's global-store replica: setup traffic, not
        # routing traffic, so it never counts toward what these tests assert.
        self.sends.clear()
        self.commands.clear()
        self.ascended.clear()
        return name

    async def stop(self) -> None:
        await self.commander.stop()
        for worker in self.workers.values():
            await worker.shutdown()

    @property
    def names(self) -> list[str]:
        return list(self.workers)

    def worker_of(self, index: int) -> UserStickyWorker:
        return self.workers[self.names[index]]

    async def new_page(self, user: str, page_id: str, worker_index: int) -> dict[str, Any]:
        """Create a page of ``user`` on a chosen worker, through the ordinary CALL.

        The user is pointed at that worker first, so sticky routing lands the
        ``new_page`` there; the surface learns the page from the fold, as always.
        """
        self.commander.assign_user(user, self.names[worker_index])
        return await self.commander.forward_call(
            user, "/op/new_page", {"page_id": page_id, "connection_id": f"s-{page_id}"}
        )

    async def subscribe_page(self, user: str, page_id: str, prefix: str) -> Any:
        """Open the page's own store on ``prefix`` — its collector is born empty."""
        return await self.commander.forward_call(
            user,
            "/op/setStoreSubscription",
            {"page_id": page_id, "storename": "page", "prefix": prefix},
        )

    async def set_datachange(self, producer: str, **kwargs: Any) -> Any:
        """The addressed write, issued by ``producer``'s own worker."""
        return await self.commander.forward_call(producer, "/op/set_datachange", kwargs)


@pytest.fixture
async def pool() -> Any:
    running = Routed()
    await running.start()
    try:
        yield running
    finally:
        await running.stop()


# ----------------------------------------------------------------------
# Tier 2: a target on the producer's own worker never touches the channel
# ----------------------------------------------------------------------


async def test_a_target_on_my_worker_is_written_locally(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("alice", "p2", 0)
    change = a_change()

    await pool.set_datachange("alice", change=parcel(change), kind="page_store", target="p2")

    page = pool.worker_of(0).page_items.get("p2")
    assert page["store"]["gnr.x"] == 42
    assert pool.sends == []
    assert pool.worker_of(0).outbox.pending() == 0


async def test_replace_coalesces_the_pending_deposits_of_one_key(pool: Routed) -> None:
    """The daemon's dedup: same path, same reason, same fired — one pending change."""
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("alice", "p2", 0)
    page = pool.worker_of(0).page_items.get("p2")

    for value in (1, 2, 3):
        await pool.set_datachange(
            "alice", change=parcel(a_change(value=value)), kind="page", target="p2", replace=True
        )

    deposited = page["collector"].drain()
    assert [c["key"]["path"] for c in deposited] == ["gnr.x"]
    assert deposited[0]["value"] == 3


async def test_without_replace_every_deposit_stays_pending(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("alice", "p2", 0)
    page = pool.worker_of(0).page_items.get("p2")

    for value in (1, 2, 3):
        await pool.set_datachange(
            "alice", change=parcel(a_change(value=value)), kind="page", target="p2"
        )

    assert [c["value"] for c in page["collector"].drain()] == [1, 2, 3]


async def test_replace_travels_on_the_ascending_message(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)

    await pool.set_datachange(
        "alice", change=parcel(a_change()), kind="page", target="p2", replace=True
    )

    await until(lambda: pool.sends)
    _, _, batch = pool.sends[0]
    assert batch[0]["replace"] is True


async def test_my_own_user_store_is_written_locally(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    change = a_change("prefs.theme", "dark")

    await pool.set_datachange("alice", change=parcel(change), kind="user_store", target="alice")

    assert pool.worker_of(0).user_items.get("alice")["store"]["prefs.theme"] == "dark"
    assert pool.sends == []


async def test_my_own_connection_store_is_written_locally(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    change = a_change("device.width", 1280)

    await pool.set_datachange(
        "alice", change=parcel(change), kind="connection_store", target="s-p1"
    )

    assert pool.worker_of(0).connection_items.get("s-p1")["store"]["device.width"] == 1280
    assert pool.sends == []


async def test_a_connection_store_write_is_never_delivered_to_a_page(pool: Routed) -> None:
    """Server-side only: no view, no collector, nothing on the browser rail."""
    await pool.new_page("alice", "p1", 0)
    change = a_change("device.width", 1280)

    await pool.set_datachange(
        "alice", change=parcel(change), kind="connection_store", target="s-p1"
    )

    page = pool.worker_of(0).page_items.get("p1")
    assert page["collector"].pending == 0
    assert page["user_view"] is None
    drained = pool.worker_of(0).collect_page("p1")
    assert drained["datachanges"] == []


async def test_a_local_signal_deposits_without_writing_the_store(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("alice", "p2", 0)
    change = a_change()

    await pool.set_datachange("alice", change=parcel(change), kind="page", target="p2")

    page = pool.worker_of(0).page_items.get("p2")
    deposited = page["collector"].drain()
    assert [c["key"]["path"] for c in deposited] == ["gnr.x"]
    assert page["store"]["gnr.x"] is None
    assert pool.sends == []


# ----------------------------------------------------------------------
# Tier 3: the target elsewhere ascends, is resolved, comes back down
# ----------------------------------------------------------------------


async def test_a_cross_worker_state_write_lands_with_the_original_ts(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.subscribe_page("bob", "p2", "gnr")
    change = a_change()

    await pool.set_datachange("alice", change=parcel(change), kind="page_store", target="p2")

    store = pool.worker_of(1).page_items.get("p2")["store"]
    await until(lambda: store["gnr.x"] == 42)
    # A real write at the destination: the producer's instant travels as an
    # attribute, the local capture keeps its own later change_ts.
    assert store.get_node("gnr.x").attr["_original_ts"] == wire_ts(change)
    landed = pool.worker_of(1).page_items.get("p2")["collector"].drain()
    assert [c["key"]["path"] for c in landed] == ["gnr", "gnr.x"]
    assert landed[-1]["change_ts"] > change["change_ts"]
    assert [(name, path) for name, path, _ in pool.sends] == [
        (pool.names[1], "/datachange_in")
    ]


async def test_a_remote_target_produced_in_a_call_rides_that_calls_reply(
    pool: Routed,
) -> None:
    """The task sub-envelope: born inside a CALL, the command travels on its REPLY."""
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.subscribe_page("bob", "p2", "gnr")

    await pool.set_datachange("alice", change=parcel(a_change()), kind="page_store", target="p2")

    assert pool.ascended == []
    assert [command["op"] for command in pool.commands] == ["set_datachange"]
    assert pool.commands[0]["worker"] == pool.names[0]
    store = pool.worker_of(1).page_items.get("p2")["store"]
    await until(lambda: store["gnr.x"] == 42)


async def test_a_remote_target_produced_outside_a_call_rides_the_outbox(
    pool: Routed,
) -> None:
    """No CALL being served, no task class: the outbox is the rail, as before."""
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.subscribe_page("bob", "p2", "gnr")
    pool.commands.clear()

    pool.worker_of(0).set_datachange(
        "alice", parcel(a_change()), kind="page_store", target="p2"
    )

    assert [event["op"] for event in pool.ascended] == ["set_datachange"]
    store = pool.worker_of(1).page_items.get("p2")["store"]
    await until(lambda: store["gnr.x"] == 42)
    assert pool.commands == []


async def test_the_tasks_of_an_error_reply_are_run_all_the_same() -> None:
    """The worker already drained what they carry: the op outcome gates neither."""
    commander = UserStickyCommander(workers=0)
    folded: list[dict[str, Any]] = []

    async def recording_fold(worker: str, message: dict[str, Any]) -> None:
        folded.append(message)

    commander.fold_command = recording_fold  # type: ignore[method-assign]
    command = {"op": "set_datachange", "seq": 1, "worker": "w-1", "kind": "page", "target": "p2"}

    with pytest.raises(ChannelCallError):
        await commander.unwrap_reply(
            "w-1", "/op/set_datachange", {"events": [], "tasks": [command], "error": "boom"}
        )

    await until(lambda: folded == [command])


async def test_a_cross_worker_user_store_write_reaches_its_user(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    change = a_change("prefs.theme", "dark")

    await pool.set_datachange("alice", change=parcel(change), kind="user_store", target="bob")

    store = pool.worker_of(1).user_items.get("bob")["store"]
    await until(lambda: store["prefs.theme"] == "dark")
    assert store.get_node("prefs.theme").attr["_original_ts"] == wire_ts(change)


async def test_a_cross_worker_connection_store_write_reaches_its_connection(
    pool: Routed,
) -> None:
    """The surface resolves a session id in two hops: connection → user → worker."""
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    change = a_change("device.width", 1280)

    await pool.set_datachange(
        "alice", change=parcel(change), kind="connection_store", target="s-p2"
    )

    store = pool.worker_of(1).connection_items.get("s-p2")["store"]
    await until(lambda: store["device.width"] == 1280)
    assert store.get_node("device.width").attr["_original_ts"] == wire_ts(change)


async def test_a_cross_worker_signal_keeps_the_producer_ts_and_leaves_no_residue(
    pool: Routed,
) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    change = a_change()

    await pool.set_datachange("alice", change=parcel(change), kind="page", target="p2")

    page = pool.worker_of(1).page_items.get("p2")
    await until(lambda: page["collector"].pending == 1)
    deposited = page["collector"].drain()
    assert [c["key"]["path"] for c in deposited] == ["gnr.x"]
    # A deposit, not a write: the producer's instant IS the change_ts and the
    # target store never learned about it.
    assert deposited[0]["change_ts"] == wire_ts(change)
    assert page["store"]["gnr.x"] is None


async def test_a_dead_target_is_dropped_with_a_log(
    pool: Routed, caplog: pytest.LogCaptureFixture
) -> None:
    await pool.new_page("alice", "p1", 0)

    with caplog.at_level(logging.DEBUG, logger="genro_asgi.spa.commander"):
        await pool.set_datachange("alice", change=parcel(a_change()), kind="page", target="ghost")
        await until(lambda: "exchange dropped" in caplog.text)

    assert pool.sends == []


async def test_a_target_that_left_the_destination_is_dropped_there(
    pool: Routed, caplog: pytest.LogCaptureFixture
) -> None:
    """The batch was already on the wire when the page went away."""
    await pool.new_page("alice", "p1", 0)
    destination = pool.worker_of(1)
    with caplog.at_level(logging.DEBUG, logger="genro_asgi.spa.worker"):
        await destination.apply_datachange_in(
            [
                {
                    "op": "set_datachange",
                    "kind": "page",
                    "target": "p9",
                    "change": "",
                    "filters": None,
                }
            ]
        )

    assert "datachange_in dropped" in caplog.text


# ----------------------------------------------------------------------
# The filtered broadcast: resolved on the surface, one send per worker
# ----------------------------------------------------------------------


async def test_a_star_broadcast_reaches_every_page_one_send_per_worker(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.new_page("bob", "p3", 1)

    await pool.set_datachange("alice", change=parcel(a_change()), kind="page", filters="*")

    await until(lambda: len(pool.sends) == 2)
    by_worker = {name: data for name, _, data in pool.sends}
    assert sorted(by_worker) == sorted(pool.names)
    # One send per destination worker, whatever the batch holds.
    assert [item["target"] for item in by_worker[pool.names[0]]] == ["p1"]
    assert sorted(item["target"] for item in by_worker[pool.names[1]]) == ["p2", "p3"]
    for page_id, worker in (("p1", 0), ("p2", 1), ("p3", 1)):
        page = pool.worker_of(worker).page_items.get(page_id)
        await until(lambda page=page: page["collector"].pending == 1)


async def test_a_user_filter_reaches_only_that_users_pages(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.new_page("bob", "p3", 1)

    await pool.set_datachange("alice", change=parcel(a_change()), kind="page", filters="user:bob")

    await until(lambda: len(pool.sends) == 1)
    name, path, batch = pool.sends[0]
    assert (name, path) == (pool.names[1], "/datachange_in")
    assert sorted(item["target"] for item in batch) == ["p2", "p3"]
    assert pool.worker_of(0).page_items.get("p1")["collector"].pending == 0


async def test_a_multi_pair_expression_is_refused_not_silently_empty(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)

    with pytest.raises(ValueError, match="one field:value pair"):
        pool.commander.matching_pages(f"user:bob AND worker:{pool.names[1]}")


def surface_page(commander: UserStickyCommander, page_id: str, user: str, connection: str) -> None:
    """Hang one page on a bare surface: every written edge of its chain, on ``W:w-1``."""
    commander.page_connection[page_id] = connection
    commander.connection_pages.setdefault(connection, set()).add(page_id)
    commander.connection_user[connection] = user
    commander.user_connections.setdefault(user, set()).add(connection)
    commander.user_worker_map[user] = "W:w-1"


def test_a_filter_value_is_a_prefix_anchored_pattern_like_the_daemons() -> None:
    # re.match, transcribed from checkpage (siteregister.py:450-456): the
    # expression is anchored at the start, so it reaches what it prefixes
    commander = UserStickyCommander(workers=0)
    surface_page(commander, "p1", "mario", "s1")
    surface_page(commander, "p2", "mariolino", "s2")

    assert sorted(page_id for page_id, _ in commander.matching_pages("user:mario")) == ["p1", "p2"]
    assert [page_id for page_id, _ in commander.matching_pages("user:mario$")] == ["p1"]
    assert [page_id for page_id, _ in commander.matching_pages("user:lino")] == []


def test_a_filter_on_a_field_the_walk_does_not_derive_matches_nothing() -> None:
    commander = UserStickyCommander(workers=0)
    surface_page(commander, "p1", "alice", "s1")

    assert commander.matching_pages("connection_id:s1") == []
    assert [page_id for page_id, _ in commander.matching_pages("*")] == ["p1"]


def test_an_invalid_pattern_is_no_match_never_an_error() -> None:
    # the daemon swallows the compile failure and answers "no match"
    commander = UserStickyCommander(workers=0)
    surface_page(commander, "p1", "a(", "s1")
    surface_page(commander, "p2", "anything", "s2")

    assert commander.matching_pages("user:a(") == []
    assert sorted(page_id for page_id, _ in commander.matching_pages("user:a.*")) == ["p1", "p2"]


def test_an_empty_derived_field_matches_nothing() -> None:
    # checkpage returns None on a falsy value before it ever compiles
    commander = UserStickyCommander(workers=0)
    surface_page(commander, "p1", "alice", "s1")
    commander.user_worker_map.pop("alice")

    assert commander.matching_pages("worker:W:w-1") == []
    assert [page_id for page_id, _ in commander.matching_pages("user:alice")] == ["p1"]


async def test_a_filtered_address_names_pages_never_a_store(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)

    with pytest.raises(Exception, match="a filtered address names pages"):
        await pool.set_datachange(
            "alice", change=parcel(a_change()), kind="user_store", filters="*"
        )


# ----------------------------------------------------------------------
# The other two EXCHANGE ops ride the very same switch
# ----------------------------------------------------------------------


async def test_reset_datachanges_empties_a_local_page(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.subscribe_page("alice", "p1", "form")
    page = pool.worker_of(0).page_items.get("p1")
    page["store"]["form.name"] = "Ada"
    assert page["collector"].pending == 2

    await pool.commander.forward_call("alice", "/op/reset_datachanges", {"target": "p1"})

    assert page["collector"].pending == 0
    assert pool.sends == []


async def test_drop_datachanges_removes_only_what_sits_under_the_path(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.subscribe_page("alice", "p1", "form")
    await pool.subscribe_page("alice", "p1", "other")
    page = pool.worker_of(0).page_items.get("p1")
    page["store"]["form.name"] = "Ada"
    page["store"]["other.x"] = 1

    await pool.commander.forward_call(
        "alice", "/op/drop_datachanges", {"target": "p1", "path": "form"}
    )

    assert [c["key"]["path"] for c in page["collector"].drain()] == ["other", "other.x"]


async def test_reset_of_a_remote_page_rides_the_rail(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.subscribe_page("bob", "p2", "form")
    page = pool.worker_of(1).page_items.get("p2")
    page["store"]["form.name"] = "Ada"
    assert page["collector"].pending == 2

    await pool.commander.forward_call("alice", "/op/reset_datachanges", {"target": "p2"})

    await until(lambda: page["collector"].pending == 0)
    assert [(name, path) for name, path, _ in pool.sends] == [
        (pool.names[1], "/datachange_in")
    ]


# ----------------------------------------------------------------------
# The shape of what travels: a readable header, a parcel nobody opens
# ----------------------------------------------------------------------


async def test_the_ascending_message_is_a_readable_header(pool: Routed) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    change = a_change()

    await pool.set_datachange("alice", change=parcel(change), kind="page", target="p2")

    await until(lambda: pool.sends)
    _, _, batch = pool.sends[0]
    item = batch[0]
    assert item["op"] == "set_datachange"
    assert item["kind"] == "page"
    assert item["target"] == "p2"
    assert item["filters"] is None
    # The change itself never left its TYTX form on the way through.
    assert item["change"] == parcel(change)


async def test_the_producers_own_pull_delivery_still_rides_the_reply(pool: Routed) -> None:
    """``page_id`` in the kwargs is the CALLER's page, never the write's target."""
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("alice", "p2", 0)
    producer = pool.worker_of(0).page_items.get("p1")
    producer["store"]["form.name"] = "Ada"

    envelope = await pool.commander.forward_envelope(
        "alice",
        "/op/set_datachange",
        {"change": parcel(a_change()), "kind": "page", "target": "p2", "page_id": "p1"},
    )

    assert envelope["result"]["target"] == "p2"
    assert "datachanges" in envelope
    # The target's own deposit stayed with the target: it was not stolen by the
    # producer's REPLY.
    assert pool.worker_of(0).page_items.get("p2")["collector"].pending == 1


# ----------------------------------------------------------------------
# The expiry rail: a drop nobody asked for, folded on the surface
# ----------------------------------------------------------------------


async def test_the_sweeps_cascade_ascends_alone_and_the_surface_folds_it(pool: Routed) -> None:
    """No CALL caused it, so the whole cascade rides the outbox and lands folded."""
    await pool.new_page("alice", "p1", 0)
    worker = pool.worker_of(0)
    worker.page_items.get("p1")["last_refresh_ts"] -= PAGE_MAX_AGE + 1

    assert worker.sweep_expired()["pages"] == ["p1"]

    await until(lambda: "p1" not in pool.commander.page_connection)
    assert [event["op"] for event in pool.ascended] == [
        "drop_page",
        "drop_connection",
        "drop_user",
    ]
    assert pool.commands == []
    assert "alice" not in pool.commander.user_worker_map
