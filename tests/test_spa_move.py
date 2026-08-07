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

"""Reception, sticky routing, the push login and its placement — baggage included.

The pool here is real but in-process: two ``UserStickyWorker`` attached to the
commander's own hub over ``LocalChannel`` pairs, so every frame still crosses
encode/decode and the placement happens over ordinary CALLs — only the fork is
missing. One subprocess smoke at the end proves the same sequence survives a
real socket and a real child.

The placement decisions are pure bookkeeping and are asserted without a wire
at all.

Then comes the move of a LIVE user: the stores, the subscriptions and everything
still pending travel in the package, and the destination is asserted on what a
page really reads — the pull delivery of its first CALL there.
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any

import pytest
from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_routes import route

from genro_tytx import from_tytx, to_tytx

from genro_asgi.channel.hub import ChannelCallError
from genro_asgi.channel.local import LocalChannel
from genro_asgi.spa.commander import UserStickyCommander
from genro_asgi.spa.worker import UserStickyWorker

SPAWN_TIMEOUT = 15.0


async def until(predicate: Any, timeout: float = SPAWN_TIMEOUT) -> None:
    """Await a condition without blocking the loop."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise TimeoutError("condition never became true")
        await asyncio.sleep(0.01)


class InstallProbe:
    """Sit on the placement's install CALL: hold it, or answer it with an error.

    Everything else goes straight through to the real hub, so the rest of the
    flow is untouched — this only makes the window in which the flag is up wide
    enough to observe, and the install failure deterministic.
    """

    def __init__(self, commander: UserStickyCommander) -> None:
        self.commander = commander
        self.hub_call = commander.hub.call
        self.arrived = asyncio.Event()
        self.gate = asyncio.Event()
        self.gate.set()
        self.error: str | None = None
        self.destinations: list[str] = []
        commander.hub.call = self.call  # type: ignore[method-assign]

    async def call(
        self, name: str, path: str, data: Any = None, timeout: float | None = None
    ) -> Any:
        if not path.endswith("install_package"):
            return await self.hub_call(name, path, data, timeout=timeout)
        self.destinations.append(name)
        self.arrived.set()
        await self.gate.wait()
        if self.error is not None:
            return {"events": [], "error": self.error}
        return await self.hub_call(name, path, data, timeout=timeout)

    def hold(self) -> None:
        """Park every install from now on."""
        self.gate.clear()

    def release(self) -> None:
        """Let the parked installs through."""
        self.gate.set()


class PageWorker(UserStickyWorker):
    """A worker with one page-addressed op: the vehicle of a pull drain.

    An applicative CALL naming its page is how a client collects what is pending
    for it, so this is what the destination of a move is asked with.
    """

    @route()
    def page_ping(self, identity: str, page_id: str) -> dict[str, Any]:
        """Address a page and do nothing else — the REPLY carries its drain."""
        return {"identity": identity, "page_id": page_id}

    @route()
    def subscribe_prefix(self, identity: str, page_id: str, prefix: str) -> dict[str, Any]:
        """Widen the calling page's view of its user store — the Q-A subscription."""
        with self.dispatch_lock:
            self.registry.subscribe_store_path(page_id, prefix)
        return {"page_id": page_id, "prefix": prefix}


class LocalPool:
    """A commander whose workers live in this process, on LocalChannel pairs.

    The workers are wired exactly like spawned ones — a roster entry, a REGISTER
    over the channel, the same fold — with ``process=None`` where the OS handle
    would be. Phase 7 turns this wiring into the commander's own single role.
    """

    def __init__(
        self, worker_class: type[UserStickyWorker] = UserStickyWorker, **kwargs: Any
    ) -> None:
        self.worker_class = worker_class
        self.commander = UserStickyCommander(workers=0, **kwargs)
        self.workers: dict[str, UserStickyWorker] = {}

    async def start(self, count: int) -> None:
        await self.commander.start()
        for _ in range(count):
            await self.add_worker()

    async def add_worker(self) -> str:
        name = self.commander.next_worker_name()
        self.commander.worker_roster[name] = self.commander.new_roster_row(os.getpid(), None)
        worker = self.worker_class(name)
        channel = LocalChannel(name)
        worker.attach_channel(channel)
        await channel.connect()
        await self.commander.hub.attach_local(channel)
        await worker.start()
        self.workers[name] = worker
        return name

    async def stop(self) -> None:
        await self.commander.stop()
        for worker in self.workers.values():
            await worker.shutdown()

    @property
    def names(self) -> list[str]:
        return list(self.workers)

    async def settled(self, user: str) -> None:
        """Wait until the user's placement flag has dropped."""
        await until(lambda: self.commander.user_worker_map.get(user, "") is not None)


@pytest.fixture
async def pool() -> Any:
    """Two in-process workers, the guest cap out of the way."""
    running = LocalPool(guest_occupancy_limit=1000)
    await running.start(2)
    try:
        yield running
    finally:
        await running.stop()


@pytest.fixture
def commander(tmp_path: Any) -> UserStickyCommander:
    """A commander whose hub is never started: placement needs no wire."""
    return UserStickyCommander(workers=0, path=str(tmp_path / "hub.sock"))


def enroll(commander: UserStickyCommander, name: str, status: str = "active") -> str:
    """Put one worker in the roster without spawning anything."""
    commander.worker_roster[name] = commander.new_roster_row(0, None)
    commander.worker_roster[name]["status"] = status
    return name


# ----------------------------------------------------------------------
# Reception, sticky resolution and the capacity check — no wire needed
# ----------------------------------------------------------------------


def test_the_reception_is_the_first_active_worker(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1", status="nascent")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    assert commander.reception == "W:w-2"


def test_a_guest_goes_to_the_reception(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    assert commander.worker_for("nobody-knows-me") == "W:w-1"


def test_a_known_user_is_sticky_to_its_own_worker(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-2")
    assert commander.worker_for("alice") == "W:w-2"


def test_a_user_whose_worker_died_falls_back_to_the_reception(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-2")
    commander.worker_roster["W:w-2"]["status"] = "dead"
    assert commander.worker_for("alice") == "W:w-1"


def test_with_no_active_worker_there_is_nowhere_to_go(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1", status="nascent")
    with pytest.raises(RuntimeError, match="no worker available"):
        commander.worker_for("alice")


def test_a_login_is_placed_on_the_least_loaded_worker(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    for user in ("a", "b", "c"):
        commander.assign_user(user, "W:w-1")
    commander.assign_user("d", "W:w-2")
    assert commander.decide_worker() == "W:w-2"


def test_the_reception_filling_up_widens_the_pool(commander: UserStickyCommander) -> None:
    commander.guest_occupancy_limit = 3
    enroll(commander, "W:w-1")
    for user in ("a", "b"):
        commander.assign_user(user, "W:w-1")
    commander.check_capacity()
    assert commander.target == 0
    commander.assign_user("c", "W:w-1")
    commander.check_capacity()
    assert commander.target == 1


def test_the_capacity_check_waits_for_a_spawn_already_in_flight(
    commander: UserStickyCommander,
) -> None:
    commander.guest_occupancy_limit = 1
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2", status="nascent")
    commander.assign_user("a", "W:w-1")
    commander.check_capacity()
    assert commander.target == 0


def test_the_capacity_check_never_passes_max_workers(commander: UserStickyCommander) -> None:
    commander.guest_occupancy_limit = 1
    commander.max_workers = 1
    commander.target = 1
    enroll(commander, "W:w-1")
    commander.assign_user("a", "W:w-1")
    commander.check_capacity()
    assert commander.target == 1


def test_the_dual_index_follows_every_re_pointing(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-1")
    commander.assign_user("alice", "W:w-2")
    assert commander.users_on("W:w-1") == set()
    assert commander.users_on("W:w-2") == {"alice"}
    commander.remove_user("alice")
    assert commander.users_on("W:w-2") == set()


def test_a_login_re_keys_the_sticky_map_and_raises_the_flag(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    commander.fold_events(
        "W:w-1",
        [
            {"op": "new_user", "seq": 1, "user": "sess-1"},
            {
                "op": "change_connection_user",
                "seq": 2,
                "user": "alice",
                "previous_user": "sess-1",
                "session_id": "sess-1",
            },
        ],
    )
    # The announcing worker pushed the user out, so it holds neither key: alice
    # is in the map under the flag and on no row until the placement lands.
    assert commander.user_worker_map == {"alice": None}
    assert commander.users_on("W:w-1") == set()


def test_the_fold_returns_the_logins_it_applied(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    batch = [
        {"op": "new_user", "seq": 1, "user": "sess-1"},
        {
            "op": "change_connection_user",
            "seq": 2,
            "user": "alice",
            "previous_user": "sess-1",
            "session_id": "sess-1",
        },
    ]
    assert [e["seq"] for e in commander.fold_events("W:w-1", batch)] == [2]


# ----------------------------------------------------------------------
# The live calls, written under the user they belong to
# ----------------------------------------------------------------------


def test_a_call_is_written_under_its_user_until_it_closes(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    request_id = commander.open_request("W:w-1", "alice", "/op/new_user")
    pending = commander.worker_roster["W:w-1"]["users"]["alice"]["pending"]
    assert pending[request_id]["path"] == "/op/new_user"
    commander.close_request("W:w-1", "alice", request_id)
    assert pending == {}


def test_a_placed_user_carries_its_live_calls_to_the_destination(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-1")
    request_id = commander.open_request("W:w-1", "alice", "/op/new_user")
    commander.assign_user("alice", "W:w-2")
    assert list(commander.worker_roster["W:w-2"]["users"]["alice"]["pending"]) == [request_id]
    assert commander.users_on("W:w-1") == set()


def test_closing_a_call_of_a_swept_user_is_a_no_op(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    commander.assign_user("alice", "W:w-1")
    request_id = commander.open_request("W:w-1", "alice", "/op/new_user")
    commander.sweep_worker("W:w-1")
    commander.close_request("W:w-1", "alice", request_id)
    assert commander.users_on("W:w-1") == set()


def test_a_user_whose_placement_is_in_flight_is_not_routed(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    commander.user_worker_map["alice"] = None
    with pytest.raises(RuntimeError, match="in flight"):
        commander.worker_for("alice")


async def test_a_waiter_that_wakes_into_a_re_raised_flag_parks_again(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.user_worker_map["alice"] = None
    parked = asyncio.create_task(commander.resolve_worker("alice"))
    await asyncio.sleep(0)
    # await_placement's inner while re-checks the map on every wakeup: the first
    # placement lands and a second login re-raises the flag before the waiter
    # reads it, so await_placement parks again on its own.
    commander.assign_user("alice", "W:w-1")
    commander.release_placement()
    commander.user_worker_map["alice"] = None
    await asyncio.sleep(0)
    assert not parked.done()
    # It resolves to the worker the last placement chose.
    commander.assign_user("alice", "W:w-2")
    commander.release_placement()
    assert await parked == "W:w-2"


# ----------------------------------------------------------------------
# The push login over two in-process workers
# ----------------------------------------------------------------------


async def test_a_guest_call_lands_on_the_reception(pool: Any) -> None:
    reception = pool.commander.reception
    entry = await pool.commander.forward_call("sess-1", "/op/new_user")
    assert entry["register_item_id"] == "sess-1"
    assert pool.commander.user_worker_map == {"sess-1": reception}
    assert pool.workers[reception].user_items.get("sess-1") is not None


async def test_the_login_returns_only_once_the_room_is_ready(pool: Any) -> None:
    source = pool.commander.reception
    target = next(name for name in pool.names if name != source)
    # Ballast on the reception so the second worker is the least loaded one.
    pool.commander.assign_user("ballast", source)
    await pool.commander.forward_call("sess-1", "/op/new_connection")
    entry = await pool.commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    # Everything below is true AT RETURN TIME: the guest is told its number
    # only after the room has been made.
    assert entry["register_item_id"] == "alice"
    assert pool.commander.user_worker_map["alice"] == target
    assert pool.workers[target].user_items.get("alice")["tag"] == "carried"
    assert pool.workers[source].user_items.get("alice") is None
    assert pool.workers[source].user_items.get("sess-1") is None


async def test_a_login_that_lands_back_home_still_travels(pool: Any) -> None:
    source = pool.commander.reception
    other = next(name for name in pool.names if name != source)
    # Load the other worker so the reception is the least loaded one.
    pool.commander.assign_user("ballast", other)
    await pool.commander.forward_call("sess-1", "/op/new_connection")
    await pool.commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    # One road, even back to where it started: alice left and was reinstalled,
    # so her entry is a fresh one carrying the same fields.
    assert pool.commander.user_worker_map["alice"] == source
    assert pool.workers[source].user_items.get("alice")["tag"] == "carried"


async def test_a_call_issued_while_the_flag_is_up_waits_for_the_room(pool: Any) -> None:
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    commander.assign_user("ballast", source)
    probe = InstallProbe(commander)
    probe.hold()
    await commander.forward_call("sess-1", "/op/new_connection")
    login = asyncio.create_task(
        commander.forward_call(
            "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
        )
    )
    await probe.arrived.wait()
    assert commander.user_worker_map["alice"] is None
    parked = asyncio.create_task(commander.forward_call("alice", "/op/drop_user"))
    await asyncio.sleep(0)
    assert not parked.done()
    probe.release()
    await login
    dropped = await parked
    # It was served by the destination, on the entry the package carried.
    assert dropped["tag"] == "carried"
    assert probe.destinations == [target]
    assert "alice" not in commander.user_worker_map


async def test_a_second_login_chains_onto_the_placement_in_flight(pool: Any) -> None:
    commander = pool.commander
    source = commander.reception
    probe = InstallProbe(commander)
    probe.hold()
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call("sess-2", "/op/new_connection")
    first = asyncio.create_task(
        commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    )
    await probe.arrived.wait()
    probe.arrived.clear()
    second = asyncio.create_task(
        commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    )
    await probe.arrived.wait()
    probe.release()
    await first
    await second
    # Two placements, one final worker and no flag left standing.
    assert len(probe.destinations) == 2
    worker = commander.user_worker_map["alice"]
    assert worker is not None
    assert commander.users_on(worker) == {"alice"}
    assert pool.workers[source].user_items.get("sess-1") is None
    assert pool.workers[source].user_items.get("sess-2") is None


async def test_an_install_that_fails_leaves_the_user_nowhere(pool: Any) -> None:
    commander = pool.commander
    source = commander.reception
    probe = InstallProbe(commander)
    probe.error = "install refused"
    await commander.forward_call("sess-1", "/op/new_connection")
    with pytest.raises(ChannelCallError, match="install refused"):
        await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    # The source spent its copy pushing: there is nothing to put back.
    assert "alice" not in commander.user_worker_map
    assert pool.workers[source].user_items.get("alice") is None
    # A later call treats alice as a guest again.
    assert commander.worker_for("alice") == source


async def test_a_destination_that_dies_mid_install_leaves_the_user_nowhere(pool: Any) -> None:
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    commander.assign_user("ballast", source)
    # The destination sits on the install in a pool thread: the CALL is parked in
    # the hub with no deadline, so only the worker's death can end it.
    arrived = threading.Event()
    holding = threading.Event()

    def stall(identity: str, blob: dict[str, Any]) -> dict[str, Any]:
        arrived.set()
        holding.wait(SPAWN_TIMEOUT)
        return {}

    pool.workers[target].add_user = stall
    await commander.forward_call("sess-1", "/op/new_connection")
    login = asyncio.create_task(
        commander.forward_call(
            "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
        )
    )
    await asyncio.get_running_loop().run_in_executor(None, arrived.wait, SPAWN_TIMEOUT)
    await pool.workers[target].channel.close()
    with pytest.raises(ConnectionError, match="lost"):
        await login
    holding.set()
    # The source spent its copy pushing, the destination never installed it.
    assert "alice" not in commander.user_worker_map
    assert commander.worker_for("alice") == source


# ----------------------------------------------------------------------
# The move of a live user: stores, subscriptions and pendings travel
# ----------------------------------------------------------------------


@pytest.fixture
async def pages() -> Any:
    """The same two-worker pool, with the page-addressed op available."""
    running = LocalPool(worker_class=PageWorker, guest_occupancy_limit=1000)
    await running.start(2)
    try:
        yield running
    finally:
        await running.stop()


async def seed_live_guest(pool: Any, source: str, page_id: str = "p1") -> dict[str, Any]:
    """A guest with one live page, and everything a move has to carry.

    Two changes are left pending on purpose — one on the page's own store, one on
    the prefix of the user store the page subscribed to — plus one dbevent
    deposit, shaped by the origin worker exactly as a commit would shape it. The
    subscriptions are taken FIRST so that nothing pending is drained by the
    REPLY of the CALL that takes them.
    """
    await pool.commander.forward_call("sess-1", "/op/new_connection")
    await pool.commander.forward_call(
        "sess-1", "/op/new_page", {"page_id": page_id, "session_id": "sess-1"}
    )
    worker = pool.workers[source]
    worker.registry.subscribe_store_path(page_id, "prefs")
    await pool.commander.forward_call(
        "sess-1", "/op/subscribeTable", {"table": "orders", "page_id": page_id}
    )
    page = worker.page_items.get(page_id)
    page["store"]["counter"] = 1
    worker.user_items.get("sess-1")["store"]["prefs.theme"] = "dark"
    deposit = worker.dbevent_deposit("orders", [["ins", "42"]], None, "commit")
    worker.fan_out_local(deposit)
    return {
        "worker": worker,
        "datachanges": list(page["collector"].changes) + list(page["user_view"].changes),
        "deposit": deposit,
    }


def wire_ts(change: dict[str, Any]) -> Any:
    """The producer's instant as the CLIENT reads it, truncated to the millisecond.

    The move itself keeps the microseconds — the parcel is pickle — but the
    delivery to the page goes through ``to_tytx(..., "json")``, whose datetime
    precision is the millisecond. Nothing restamps: this is the same truncation
    the routing tests compare against.
    """
    return from_tytx(to_tytx(change, "json"), "json")["change_ts"]


async def drain_over_the_wire(pool: Any, user: str, page_id: str = "p1") -> dict[str, Any]:
    """What a page reads on its first CALL at the destination, hydrated."""
    envelope = await pool.commander.forward_envelope(user, "/op/page_ping", {"page_id": page_id})
    return {key: from_tytx(envelope[key], "json") for key in ("datachanges", "dbevents")}


async def test_the_pendings_of_a_moved_page_arrive_in_the_order_they_left(pages: Any) -> None:
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    pages.commander.assign_user("ballast", source)
    seeded = await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert pages.commander.user_worker_map["alice"] == target
    delivered = await drain_over_the_wire(pages, "alice")
    # Same changes, same order, the producer's own instants: the re-deposit
    # preserves change_ts and the destination drain follows the deposit order.
    assert [change["key"]["path"] for change in delivered["datachanges"]] == [
        change["key"]["path"] for change in seeded["datachanges"]
    ]
    assert [change["change_ts"] for change in delivered["datachanges"]] == [
        wire_ts(change) for change in seeded["datachanges"]
    ]
    # The dbevent is the deposit the origin shaped, its ts included.
    assert delivered["dbevents"] == [seeded["deposit"]]


async def test_the_hydration_of_a_moved_store_captures_nothing(pages: Any) -> None:
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    pages.commander.assign_user("ballast", source)
    seeded = await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    # The collectors are attached to Bags that arrived already full, so what is
    # pending at the destination is exactly what was shipped — not one change
    # more for the nodes the unpickling put there.
    page = pages.workers[target].page_items.get("p1")
    assert len(page["collector"].changes) == len(seeded["datachanges"])
    assert page["user_view"].changes == []


async def test_a_moved_page_lives_again_with_its_stores_and_subscriptions(pages: Any) -> None:
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    pages.commander.assign_user("ballast", source)
    await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    worker = pages.workers[target]
    page = worker.page_items.get("p1")
    assert page["store"]["counter"] == 1
    # The guest item followed its first real identity: alice's Bag IS the one
    # the guest wrote into, carried whole through the move.
    assert worker.user_items.get("alice")["store"]["prefs.theme"] == "dark"
    assert page["store_subscriptions"] == {"prefs"}
    assert page["table_subscriptions"] == {"orders"}
    assert worker.subscriptions.pages_for("orders") == {"p1"}
    assert worker.subscriptions.tables_for("p1") == {"orders"}
    # The source kept nothing: no row, no subscription, no user.
    assert pages.workers[source].page_items.get("p1") is None
    assert pages.workers[source].subscriptions.pages_for("orders") == set()
    # And the user view is alive on the Bag that arrived: a write into the
    # subscribed prefix of the moved user store is found by the moved page.
    await drain_over_the_wire(pages, "alice")
    worker.user_items.get("alice")["store"]["prefs.lang"] = "it"
    delivered = await drain_over_the_wire(pages, "alice")
    # One change, not two: the carried Bag already holds the ``prefs`` node the
    # guest brought into being, so only the leaf is new.
    assert [change["key"]["path"] for change in delivered["datachanges"]] == ["prefs.lang"]


async def test_a_dbevent_notified_after_the_move_reaches_the_moved_page(pages: Any) -> None:
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    pages.commander.assign_user("ballast", source)
    await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await drain_over_the_wire(pages, "alice")
    # The index the move rebuilt is the one the destination's own fan-out reads:
    # the moved page notifies and is served on the REPLY of that very CALL.
    envelope = await pages.commander.forward_envelope(
        "alice",
        "/op/notifyDbEvents",
        {"dbevents": {"orders": [["upd", "42"]]}, "page_id": "p1", "reason": "later"},
    )
    served = from_tytx(envelope["dbevents"], "json")
    assert [(event["table"], event["reason"]) for event in served] == [("orders", "later")]
    assert pages.workers[target].page_items.get("p1")["dbevents"] == []


async def test_an_install_that_fails_takes_the_baggage_with_the_user(pages: Any) -> None:
    source = pages.commander.reception
    probe = InstallProbe(pages.commander)
    probe.error = "install refused"
    await seed_live_guest(pages, source)
    with pytest.raises(ChannelCallError, match="install refused"):
        await pages.commander.forward_call(
            "sess-1", "/op/change_connection_user", {"user": "alice"}
        )
    # The source spent its copy pushing — the pages went with it — and the
    # destination never installed: the user is nowhere and so is its baggage.
    worker = pages.workers[source]
    assert worker.page_items.get("p1") is None
    assert worker.user_items.get("sess-1") is None
    assert worker.user_items.get("alice") is None
    assert worker.subscriptions.pages_for("orders") == set()
    assert "alice" not in pages.commander.user_worker_map


# ----------------------------------------------------------------------
# The second connection: presence before occupancy, and the install joins
# ----------------------------------------------------------------------


async def test_two_connections_of_one_user_end_up_whole_on_one_worker(pages: Any) -> None:
    commander = pages.commander
    source = commander.reception
    other = next(name for name in pages.names if name != source)
    # Ballast on the other worker, so the reception stays the least loaded one
    # and the first login lands back home: one worker, one user, two connections.
    commander.assign_user("ballast", other)
    await commander.forward_call(
        "sess-1", "/op/new_page", {"page_id": "p1", "session_id": "sess-1"}
    )
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await commander.forward_call(
        "sess-2", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"}
    )
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    # The first login travelled and was reinstalled here; the second found alice
    # already at home and only linked onto her. Either road ends on the same
    # slice: both connections, both pages, each page under its own connection.
    worker = pages.workers[commander.user_worker_map["alice"]]
    assert worker.user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    assert {worker.registry.user_of_page(page_id) for page_id in ("p1", "p2")} == {"alice"}
    assert worker.page_items.get("p1")["connection_id"] == "sess-1"
    assert worker.page_items.get("p2")["connection_id"] == "sess-2"
    assert worker.connection_items.get("sess-1")["pages"] == {"p1"}
    assert worker.connection_items.get("sess-2")["pages"] == {"p2"}


async def test_the_join_lands_the_arrival_on_the_resident_store(pages: Any) -> None:
    commander = pages.commander
    source = commander.reception
    target = next(name for name in pages.names if name != source)
    commander.assign_user("ballast", source)
    await commander.forward_call(
        "sess-1", "/op/new_page", {"page_id": "p1", "session_id": "sess-1"}
    )
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert commander.user_worker_map["alice"] == target
    resident = pages.workers[target]
    resident.user_items.get("alice")["store"]["prefs.theme"] = "dark"
    # A second guest, on the reception, logs in as the same user.
    await commander.forward_call(
        "sess-2", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"}
    )
    pages.workers[source].registry.subscribe_store_path("p2", "prefs")
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    # Presence beat occupancy: alice never moved, and the store the arrival finds
    # is the one that was already open here — the blob's copy was discarded.
    assert commander.user_worker_map["alice"] == target
    assert resident.user_items.get("alice")["store"]["prefs.theme"] == "dark"
    assert resident.user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    # And the arrival watches that very Bag: a write into it reaches p2.
    await drain_over_the_wire(pages, "alice", "p2")
    resident.user_items.get("alice")["store"]["prefs.lang"] = "it"
    delivered = await drain_over_the_wire(pages, "alice", "p2")
    assert [change["key"]["path"] for change in delivered["datachanges"]] == ["prefs.lang"]


async def test_a_failed_join_leaves_the_resident_placement_alone(pool: Any) -> None:
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    commander.assign_user("ballast", source)
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    assert commander.user_worker_map["alice"] == target
    probe = InstallProbe(commander)
    probe.error = "install refused"
    await commander.forward_call("sess-2", "/op/new_connection")
    with pytest.raises(ChannelCallError, match="install refused"):
        await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    # The arriving connection went down with its package — but alice never left:
    # the placement stands and so does everything already sitting on it.
    assert commander.user_worker_map["alice"] == target
    assert pool.workers[target].user_items.get("alice")["tag"] == "carried"
    assert pool.workers[target].user_items.get("alice")["connections"] == {"sess-1"}


async def test_only_an_unplaced_login_is_a_free_choice(pool: Any) -> None:
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    commander.assign_user("ballast", source)
    decided: list[str] = []
    choose = commander.decide_worker

    def counted() -> str:
        decided.append(choose())
        return decided[-1]

    commander.decide_worker = counted  # type: ignore[method-assign]
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    # Nobody held alice: the placement was decided by load.
    assert decided == [target]
    assert commander.user_worker_map["alice"] == target
    await commander.forward_call("sess-2", "/op/new_connection")
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    # The second connection of a placed user never asks — presence comes first.
    assert decided == [target]
    assert commander.user_worker_map["alice"] == target


# ----------------------------------------------------------------------
# The resident login: the worker already hosts the user, so nothing travels
# ----------------------------------------------------------------------


def spy_on_folded(commander: UserStickyCommander) -> list[dict[str, Any]]:
    """Record every event the commander folds — what the REPLYs carried up."""
    seen: list[dict[str, Any]] = []
    original = commander.fold_events

    def spying(worker: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen.extend(events)
        return original(worker, events)

    commander.fold_events = spying  # type: ignore[method-assign]
    return seen


async def home_bound_alice(pages: Any) -> str:
    """Alice logged in and placed back on the reception, with page p1 alive.

    Ballast on the other worker makes the reception the least loaded one, so the
    first login lands where it started — and the next guest, which the reception
    also holds, will log in AT HOME.
    """
    commander = pages.commander
    source = commander.reception
    other = next(name for name in pages.names if name != source)
    commander.assign_user("ballast", other)
    await commander.forward_call(
        "sess-1", "/op/new_page", {"page_id": "p1", "session_id": "sess-1"}
    )
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert commander.user_worker_map["alice"] == source
    return source


async def test_a_resident_login_never_takes_the_pages_off_the_worker(pages: Any) -> None:
    commander = pages.commander
    source = await home_bound_alice(pages)
    worker = pages.workers[source]
    page_row = worker.page_items.get("p1")
    page_store = page_row["store"]
    await commander.forward_call(
        "sess-2", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"}
    )
    folded = spy_on_folded(commander)
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    # p1 was never dropped: the same row, holding the same Bag, all along.
    assert worker.page_items.get("p1") is page_row
    assert worker.page_items.get("p1")["store"] is page_store
    assert worker.user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    assert commander.user_worker_map["alice"] == source
    # The login went up with no baggage: there was no room to make.
    logins = [event for event in folded if event["op"] == "change_connection_user"]
    assert [event["session_id"] for event in logins] == ["sess-2"]
    assert "package" not in logins[0]
    # And both pages are served afterwards, each on its own connection.
    for page_id in ("p1", "p2"):
        await drain_over_the_wire(pages, "alice", page_id)


async def test_only_the_login_that_ships_is_installed(pages: Any) -> None:
    commander = pages.commander
    probe = InstallProbe(commander)
    source = await home_bound_alice(pages)
    # The first login had nowhere to be: it packaged and was installed once.
    assert probe.destinations == [source]
    await commander.forward_call(
        "sess-2", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"}
    )
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    # The resident login installed nothing, because it packaged nothing.
    assert probe.destinations == [source]


async def test_traffic_to_a_resident_page_survives_a_concurrent_login(pages: Any) -> None:
    commander = pages.commander
    source = await home_bound_alice(pages)
    worker = pages.workers[source]
    await drain_over_the_wire(pages, "alice", "p1")
    worker.page_items.get("p1")["store"]["counter"] = 1
    await commander.forward_call(
        "sess-2", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"}
    )
    # The panel's repro: p1's own traffic runs while the second connection logs
    # in as alice. It used to fall into the eviction window — the subscription
    # raised on an unknown page and the pending change was lost with the row.
    login = asyncio.create_task(
        commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    )
    subscribed = asyncio.create_task(
        commander.forward_envelope(
            "alice", "/op/subscribeTable", {"table": "orders", "page_id": "p1"}
        )
    )
    drained = asyncio.create_task(
        commander.forward_envelope("alice", "/op/page_ping", {"page_id": "p1"})
    )
    await login
    envelopes = [await subscribed, await drained]
    assert envelopes[0]["result"]["table"] == "orders"
    # Both CALLs name p1, so both drain it: whichever ran first carried the
    # change, and the point is that neither lost it.
    changes = [
        change
        for envelope in envelopes
        for change in from_tytx(envelope["datachanges"], "json")
    ]
    assert [change["key"]["path"] for change in changes] == ["counter"]
    # The subscription landed on the page that never moved.
    assert worker.subscriptions.pages_for("orders") == {"p1"}


# ----------------------------------------------------------------------
# S1 and S2 end to end, over the two-worker pool
# ----------------------------------------------------------------------


def a_change(path: str, value: Any) -> dict[str, Any]:
    """One real change dict, born from a real write on a throwaway Bag."""
    bag = Bag()
    collector = DataChangeCollector(bag)
    bag.set_item(path, value)
    return collector.drain()[-1]


async def logged_in_elsewhere(pool: Any) -> tuple[str, str]:
    """Alice's guest page logs in and is placed away; bob stays on the reception.

    This is S1's own setup: the page is reached only through what the surface
    knows about it, and the producer sits on the OTHER worker so every address
    below has to cross the rail.
    """
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    commander.assign_user("ballast", source)
    await commander.forward_call(
        "sess-1", "/op/new_page", {"page_id": "p1", "session_id": "sess-1"}
    )
    await commander.forward_call(
        "sess-1", "/op/subscribeTable", {"table": "orders", "page_id": "p1"}
    )
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert commander.user_worker_map["alice"] == target
    commander.assign_user("bob", source)
    await commander.forward_call("bob", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"})
    # Clear what the move itself carried: what the assertions read afterwards is
    # only what crossed the rail after the login.
    await drain_over_the_wire(pool, "alice")
    return source, target


async def test_an_addressed_write_from_another_worker_reaches_the_moved_page(
    pages: Any,
) -> None:
    _, target = await logged_in_elsewhere(pages)

    await pages.commander.forward_call(
        "bob",
        "/op/set_datachange",
        {"change": to_tytx(a_change("gnr.x", 42), "json"), "kind": "page", "target": "p1"},
    )

    # S1: before the three registers the page row died at the login, the surface
    # could not resolve p1 any more and the message was dropped.
    page = pages.workers[target].page_items.get("p1")
    await until(lambda: page["collector"].pending == 1)
    delivered = await drain_over_the_wire(pages, "alice")
    assert [(c["key"]["path"], c["value"]) for c in delivered["datachanges"]] == [("gnr.x", 42)]


async def test_a_user_filter_matches_the_page_under_its_new_owner(pages: Any) -> None:
    source, target = await logged_in_elsewhere(pages)

    await pages.commander.forward_call(
        "bob",
        "/op/set_datachange",
        {"change": to_tytx(a_change("gnr.x", 42), "json"), "kind": "page", "filters": "user:alice"},
    )

    # The row was re-labelled, not deleted: the broadcast matches on the label
    # the login wrote, and bob's own page is outside it.
    page = pages.workers[target].page_items.get("p1")
    await until(lambda: page["collector"].pending == 1)
    delivered = await drain_over_the_wire(pages, "alice")
    assert [c["key"]["path"] for c in delivered["datachanges"]] == ["gnr.x"]
    assert pages.workers[source].page_items.get("p2")["collector"].pending == 0


async def test_a_dbevent_from_another_worker_reaches_the_moved_subscription(
    pages: Any,
) -> None:
    _, target = await logged_in_elsewhere(pages)

    await pages.commander.forward_call(
        "bob",
        "/op/notifyDbEvents",
        {"dbevents": {"orders": [["ins", "42"]]}, "page_id": "p2", "reason": "commit"},
    )

    # The subscription the page took as a guest is still its own after the login,
    # and the commander's dbevents surface still knows where p1 lives.
    page = pages.workers[target].page_items.get("p1")
    await until(lambda: page["dbevents"])
    delivered = await drain_over_the_wire(pages, "alice")
    assert [(e["table"], e["from_page_id"], e["reason"]) for e in delivered["dbevents"]] == [
        ("orders", "p2", "commit")
    ]


async def test_the_second_connection_is_served_beside_the_first(pages: Any) -> None:
    commander = pages.commander
    source = commander.reception
    target = next(name for name in pages.names if name != source)
    commander.assign_user("ballast", source)
    await commander.forward_call(
        "sess-1", "/op/new_page", {"page_id": "p1", "session_id": "sess-1"}
    )
    await commander.forward_call(
        "sess-1", "/op/subscribe_prefix", {"page_id": "p1", "prefix": "prefs"}
    )
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert commander.user_worker_map["alice"] == target
    await commander.forward_call(
        "alice",
        "/op/set_datachange",
        {
            "change": to_tytx(a_change("prefs.theme", "dark"), "json"),
            "kind": "user_store",
            "target": "alice",
        },
    )
    await drain_over_the_wire(pages, "alice", "p1")

    # S2: a second guest, on the reception, logs in as the very same user — it
    # used to raise, and the failed install took the first placement down with it.
    await commander.forward_call(
        "sess-2", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"}
    )
    await commander.forward_call(
        "sess-2", "/op/subscribe_prefix", {"page_id": "p2", "prefix": "prefs"}
    )
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})

    # Presence beat occupancy: alice never moved, and both connections are hers.
    assert commander.user_worker_map["alice"] == target
    assert pages.workers[target].user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    for page_id in ("p1", "p2"):
        await drain_over_the_wire(pages, "alice", page_id)
    await commander.forward_call(
        "alice",
        "/op/set_datachange",
        {
            "change": to_tytx(a_change("prefs.lang", "it"), "json"),
            "kind": "user_store",
            "target": "alice",
        },
    )
    # One write on one Bag, served to both connections' pages — and ONE change,
    # not two: the ``prefs`` node was already there, so the store the arrival
    # joined is the resident one, not a fresh Bag put in its place.
    for page_id in ("p1", "p2"):
        delivered = await drain_over_the_wire(pages, "alice", page_id)
        assert [c["key"]["path"] for c in delivered["datachanges"]] == ["prefs.lang"]


# ----------------------------------------------------------------------
# The same sequence over a real socket and a real child
# ----------------------------------------------------------------------


@pytest.mark.timeout(60)
async def test_the_login_survives_real_children_over_uds() -> None:
    running = UserStickyCommander(
        workers=0,
        guest_occupancy_limit=1000,
        worker_kwargs={"max_threads": 2},
    )
    await running.start()
    try:
        running.scale(2)
        await running.wait_workers_ready(2)
        source = running.reception
        target = next(name for name in running.active_workers if name != source)
        running.assign_user("ballast", source)
        await running.forward_call("sess-1", "/op/new_connection")
        entry = await running.forward_call(
            "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
        )
        assert entry["tag"] == "carried"
        assert running.user_worker_map["alice"] == target
        dropped = await running.forward_call("alice", "/op/drop_user")
        assert dropped["tag"] == "carried"
    finally:
        await running.stop()
