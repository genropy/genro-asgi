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
import logging
import os
import signal
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest
from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_routes import route

from genro_tytx import from_tytx, to_tytx

from genro_asgi.channel.hub import ChannelCallError
from genro_asgi.channel.local import LocalChannel
from genro_asgi.exceptions import HTTPException
from genro_asgi.spa.commander import (
    RECYCLE_RETRY_SECONDS,
    TOMBSTONE_SECONDS,
    UserStickyCommander,
)
from genro_asgi.spa.worker import CONNECTION_MAX_AGE
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
        if not path.endswith("add_user"):
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

    async def add_worker(self, name: str | None = None) -> str:
        if name is None:
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
    """Two in-process workers, both idle: the reception keeps until a test tilts it."""
    running = LocalPool()
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


def load(commander: UserStickyCommander, name: str, saturation: float) -> None:
    """Seed the worker's window so its cpu component reads ``saturation``.

    One reading is enough: the evaluator averages the rows it finds. cpu is
    judged against its own target, so the report carries ``saturation`` times it.
    """
    cpu = saturation * commander.evaluator.targets["cpu"]
    commander.worker_roster[name]["occupancy"].clear()
    commander.record_occupancy(
        name, {"cpu": cpu, "rss": None, "reusable": None, "executor": {"busy": 0, "total": 0}}
    )


def tilt_away(commander: UserStickyCommander, reception: str) -> None:
    """Put the reception over its threshold, so the next login is passed on.

    A ballast user rides along: a reception that keeps nobody is not what these
    paths are about, and the saturation is what actually tilts the placement.
    """
    commander.assign_user("ballast", reception)
    load(commander, reception, 0.9)


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


def test_the_reception_keeps_the_login_while_it_is_under_its_threshold(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.4)
    assert commander.decide_worker() == "W:w-1"


def test_the_sole_worker_keeps_the_login_however_saturated(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.9)
    assert commander.decide_worker() == "W:w-1"


def test_a_reception_over_its_threshold_passes_to_the_least_loaded_other(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    load(commander, "W:w-1", 0.6)
    load(commander, "W:w-2", 0.8)
    load(commander, "W:w-3", 0.3)
    assert commander.decide_worker() == "W:w-3"


def test_with_every_other_worker_past_the_gate_the_login_lands_anyway(
    commander: UserStickyCommander, caplog: Any
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    load(commander, "W:w-1", 0.6)
    load(commander, "W:w-2", 1.2)
    load(commander, "W:w-3", 1.1)
    with caplog.at_level("WARNING"):
        assert commander.decide_worker() == "W:w-3"
    assert "admission gate" in caplog.text


def test_a_pool_of_one_widens_when_its_reception_passes_the_threshold(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.4)
    commander.check_capacity()
    assert commander.target == 0
    load(commander, "W:w-1", 0.9)
    commander.check_capacity()
    assert commander.target == 1


def test_a_pool_of_many_widens_only_when_nobody_past_the_reception_admits(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 1.5)
    load(commander, "W:w-2", 0.9)
    commander.check_capacity()
    assert commander.target == 0
    load(commander, "W:w-2", 1.2)
    commander.check_capacity()
    assert commander.target == 1


def test_the_capacity_check_waits_for_a_spawn_already_in_flight(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2", status="nascent")
    load(commander, "W:w-1", 0.9)
    commander.check_capacity()
    assert commander.target == 0


def test_the_capacity_check_never_passes_max_workers(commander: UserStickyCommander) -> None:
    commander.max_workers = 1
    commander.target = 1
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.9)
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
    # carries the placing flag, and enters the map only with place_login's
    # decision — the fold itself names no destination.
    assert "alice" in commander.placing
    assert commander.user_worker_map == {}
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
    commander.placing.add("alice")
    with pytest.raises(RuntimeError, match="in flight"):
        commander.worker_for("alice")


async def test_an_arriving_login_is_visible_from_the_decision(
    commander: UserStickyCommander,
) -> None:
    """The founding contract, restored: map and half-row name the destination
    from the DECISION, while the install still travels — so no emptiness
    verdict can miss an arriving user, no late claim overrides the placement,
    and no sweep steals the arrival from its own placement coroutine."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.placing.add("alice")
    commander.assign_user("alice", "W:w-1")  # the decision; the install is on the wire
    assert "alice" in commander.users_on("W:w-1")
    assert commander.user_worker_map["alice"] == "W:w-1"
    # A claim landing inside the flight never re-points the user.
    commander.register_user("alice", "W:w-2")
    assert commander.user_worker_map["alice"] == "W:w-1"
    # The sweep of the dying destination leaves the arrival alone: the slice is
    # in the placement coroutine's hands, and its failure path owns the outcome.
    assert commander.sweep_worker("W:w-1") == []
    assert commander.user_worker_map["alice"] == "W:w-1"


async def test_a_waiter_that_wakes_into_a_re_raised_flag_parks_again(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.placing.add("alice")
    parked = asyncio.create_task(commander.resolve_worker("alice"))
    await asyncio.sleep(0)
    # await_placement's inner while re-checks the flag on every wakeup: the first
    # placement lands and a second login re-raises the flag before the waiter
    # reads it, so await_placement parks again on its own.
    commander.assign_user("alice", "W:w-1")
    commander.placing.discard("alice")
    commander.release_placement()
    commander.placing.add("alice")
    await asyncio.sleep(0)
    assert not parked.done()
    # It resolves to the worker the last placement chose.
    commander.assign_user("alice", "W:w-2")
    commander.placing.discard("alice")
    commander.release_placement()
    assert await parked == "W:w-2"


async def test_a_waiter_that_wakes_into_a_move_parks_on_it(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.placing.add("alice")
    parked = asyncio.create_task(commander.resolve_worker("alice"))
    await asyncio.sleep(0)
    # The placement lands and a move of the same user starts before the waiter is
    # scheduled: two holds read once each, in order, would let it through here
    # with the map still naming the source.
    commander.assign_user("alice", "W:w-1")
    commander.placing.discard("alice")
    commander.moving["alice"] = asyncio.Event()
    commander.release_placement()
    await asyncio.sleep(0)
    assert not parked.done()
    # It resolves the worker the move carried the user to.
    commander.assign_user("alice", "W:w-2")
    commander.release_move("alice")
    assert await parked == "W:w-2"


def test_an_identity_nothing_holds_is_resolved_without_a_wait(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    commander.assign_user("alice", "W:w-1")
    assert commander.is_held("alice") is False
    assert commander.is_held("sess-1") is False
    # Zero awaits on the no-hold path: driven by hand, the coroutine must
    # complete on the first send, never yielding control back.
    coro = commander.resolve_worker("alice")
    with pytest.raises(StopIteration) as excinfo:
        coro.send(None)
    assert excinfo.value.value == "W:w-1"


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
    tilt_away(pool.commander, source)
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
    tilt_away(commander, source)
    probe = InstallProbe(commander)
    probe.hold()
    await commander.forward_call("sess-1", "/op/new_connection")
    login = asyncio.create_task(
        commander.forward_call(
            "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
        )
    )
    await probe.arrived.wait()
    # Mid-install: the map already names the destination (visible from the
    # decision), while the placing flag is what keeps alice's calls parked.
    assert commander.user_worker_map["alice"] == target
    assert "alice" in commander.placing
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
    tilt_away(commander, source)
    # The destination sits on the install in a pool thread: the CALL is parked in
    # the hub with no deadline, so only the worker's death can end it. The stall
    # shadows install_connection — add_user itself is dispatched through the
    # route table, where an instance attribute cannot intercept it.
    arrived = threading.Event()
    holding = threading.Event()

    def stall(user: str, connection_id: str, packed: dict[str, Any]) -> None:
        arrived.set()
        holding.wait(SPAWN_TIMEOUT)

    pool.workers[target].install_connection = stall
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
    running = LocalPool(worker_class=PageWorker)
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
    worker.setStoreSubscription("sess-1", page_id=page_id, storename="page", prefix="counter")
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
    tilt_away(pages.commander, source)
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
    tilt_away(pages.commander, source)
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
    tilt_away(pages.commander, source)
    await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    worker = pages.workers[target]
    page = worker.page_items.get("p1")
    assert page["store"]["counter"] == 1
    # The guest item followed its first real identity: alice's Bag IS the one
    # the guest wrote into, carried whole through the move.
    assert worker.user_items.get("alice")["store"]["prefs.theme"] == "dark"
    assert page["store_subscriptions"] == {"prefs"}
    assert page["subscribed_paths"] == {"counter"}
    assert page["collector"].paths == {"counter"}
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


async def test_the_page_filter_survives_the_move(pages: Any) -> None:
    """``subscribed_paths`` is replayed onto the reborn collector, filter and all."""
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(pages.commander, source)
    await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    worker = pages.workers[target]
    await drain_over_the_wire(pages, "alice")
    page = worker.page_items.get("p1")
    page["store"]["counter"] = 2
    page["store"]["untold.x"] = 1
    delivered = await drain_over_the_wire(pages, "alice")
    assert [change["key"]["path"] for change in delivered["datachanges"]] == ["counter"]


async def test_the_moved_connection_carries_its_own_store(pages: Any) -> None:
    """The connection store travels inside the blob, hydrated at destination."""
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(pages.commander, source)
    await seed_live_guest(pages, source)
    pages.workers[source].connection_items.get("sess-1")["store"]["device.width"] = 1280

    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})

    arrived = pages.workers[target].connection_items.get("sess-1")
    assert arrived["store"]["device.width"] == 1280
    assert pages.workers[source].connection_items.get("sess-1") is None


async def test_a_dbevent_notified_after_the_move_reaches_the_moved_page(pages: Any) -> None:
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(pages.commander, source)
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


async def test_the_commanded_eviction_carries_what_the_login_push_carries(pages: Any) -> None:
    """``evict_user`` on order builds the same parcel, and it rebuilds the same slice."""
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(pages.commander, source)
    seeded = await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert pages.commander.user_worker_map["alice"] == target

    result = await pages.commander.forward_call("alice", "/op/evict_user")
    # The worker that answered kept nothing: the slice is in the parcel alone.
    assert pages.workers[target].user_items.get("alice") is None
    assert pages.workers[target].page_items.get("p1") is None
    assert pages.workers[target].subscriptions.pages_for("orders") == set()

    pages.commander.assign_user("alice", source)
    await pages.commander.forward_call(
        "alice", "/op/add_user", {"encoded": result["encoded"]}
    )
    worker = pages.workers[source]
    page = worker.page_items.get("p1")
    assert page["store"]["counter"] == 1
    assert page["subscribed_paths"] == {"counter"}
    assert page["store_subscriptions"] == {"prefs"}
    assert page["table_subscriptions"] == {"orders"}
    assert worker.subscriptions.pages_for("orders") == {"p1"}
    assert worker.user_items.get("alice")["store"]["prefs.theme"] == "dark"
    assert worker.connection_items.get("sess-1")["user"] == "alice"
    # Nothing pending was lost on the way: the two changes and the deposit that
    # left with the login are still what the page reads at the arrival.
    delivered = await drain_over_the_wire(pages, "alice")
    assert [change["key"]["path"] for change in delivered["datachanges"]] == [
        change["key"]["path"] for change in seeded["datachanges"]
    ]
    assert delivered["dbevents"] == [seeded["deposit"]]


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
    assert {worker.registry.page_user(page_id) for page_id in ("p1", "p2")} == {"alice"}
    assert worker.page_items.get("p1")["connection_id"] == "sess-1"
    assert worker.page_items.get("p2")["connection_id"] == "sess-2"
    assert worker.connection_items.get("sess-1")["pages"] == {"p1"}
    assert worker.connection_items.get("sess-2")["pages"] == {"p2"}


async def test_the_join_lands_the_arrival_on_the_resident_store(pages: Any) -> None:
    commander = pages.commander
    source = commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(commander, source)
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
    tilt_away(commander, source)
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
    tilt_away(commander, source)
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
    assert "encoded" not in logins[0]
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
    worker.setStoreSubscription("alice", page_id="p1", storename="page", prefix="counter")
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
    tilt_away(commander, source)
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
    tilt_away(commander, source)
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
# The move the commander ORDERS: flag, quiesce, custody, switch
# ----------------------------------------------------------------------


class RefuseInstall:
    """Refuse every install addressed to the named workers; pass everything else.

    The deterministic form of a destination dying with the parcel in the air:
    what the commander does next is look for another room.
    """

    def __init__(self, commander: UserStickyCommander, refused: list[str]) -> None:
        self.commander = commander
        self.hub_call = commander.hub.call
        self.refused = set(refused)
        self.destinations: list[str] = []
        commander.hub.call = self.call  # type: ignore[method-assign]

    async def call(
        self, name: str, path: str, data: Any = None, timeout: float | None = None
    ) -> Any:
        if not path.endswith("add_user"):
            return await self.hub_call(name, path, data, timeout=timeout)
        self.destinations.append(name)
        if name in self.refused:
            return {"events": [], "error": "no room here"}
        return await self.hub_call(name, path, data, timeout=timeout)


@pytest.fixture
async def impatient() -> Any:
    """The page pool with a quiesce budget short enough to expire inside a test."""
    running = LocalPool(
        worker_class=PageWorker, move_quiesce_timeout=0.1
    )
    await running.start(2)
    try:
        yield running
    finally:
        await running.stop()


async def seed_moving_user(pool: Any, page_id: str = "p1") -> str:
    """A logged user with one live page; returns the worker it landed on."""
    await seed_live_guest(pool, pool.commander.reception, page_id)
    await pool.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    return str(pool.commander.user_worker_map["alice"])


def other_than(pool: Any, *taken: str) -> str:
    """Any worker of the pool that is none of ``taken``."""
    return next(name for name in pool.names if name not in taken)


async def test_a_commanded_move_carries_the_whole_slice(pages: Any) -> None:
    commander = pages.commander
    source = await seed_moving_user(pages)
    target = other_than(pages, source)
    assert await commander.move_user("alice", target) is True
    assert commander.user_worker_map["alice"] == target
    assert commander.users_on(target) == {"alice"}
    assert pages.workers[source].user_items.get("alice") is None
    # Everything the login push carries, the commanded move carries too.
    worker = pages.workers[target]
    assert worker.user_items.get("alice")["store"]["prefs.theme"] == "dark"
    page = worker.page_items.get("p1")
    assert page["store"]["counter"] == 1
    assert page["store_subscriptions"] == {"prefs"}
    assert page["table_subscriptions"] == {"orders"}
    assert "alice" not in commander.moving


async def test_a_call_issued_during_a_move_is_served_by_the_destination(pages: Any) -> None:
    commander = pages.commander
    source = await seed_moving_user(pages)
    target = other_than(pages, source)
    await drain_over_the_wire(pages, "alice")
    probe = InstallProbe(commander)
    probe.hold()
    move = asyncio.create_task(commander.move_user("alice", target))
    await probe.arrived.wait()
    # The map still points at the source: nothing is routed off a half-done move.
    assert commander.user_worker_map["alice"] == source
    parked = asyncio.create_task(
        commander.forward_call("alice", "/op/page_ping", {"page_id": "p1"})
    )
    await asyncio.sleep(0)
    assert not parked.done()
    probe.release()
    assert await move is True
    # It waited for the room and was answered by the worker that got it — the
    # source has no page p1 left to answer with.
    assert (await parked)["page_id"] == "p1"
    assert probe.destinations == [target]
    assert pages.workers[source].page_items.get("p1") is None


async def test_a_store_change_addressed_during_a_move_lands_on_the_destination(
    pages: Any,
) -> None:
    commander = pages.commander
    source = await seed_moving_user(pages)
    target = other_than(pages, source)
    await drain_over_the_wire(pages, "alice")
    commander.assign_user("bob", source)
    probe = InstallProbe(commander)
    probe.hold()
    move = asyncio.create_task(commander.move_user("alice", target))
    await probe.arrived.wait()
    # The slice has already left the source and the map still names it: an
    # address resolved now would be shipped to a worker that no longer holds
    # alice, and the change would be gone for good.
    assert pages.workers[source].user_items.get("alice") is None
    await commander.forward_call(
        "bob",
        "/op/set_datachange",
        {
            "change": to_tytx(a_change("prefs.lang", "it"), "json"),
            "kind": "user_store",
            "target": "alice",
        },
    )
    await asyncio.sleep(0)
    probe.release()
    assert await move is True
    # It was held, not dropped: past the barrier the map names the destination,
    # and the write lands on the store that travelled there.
    await until(lambda: pages.workers[target].user_items.get("alice")["store"]["prefs.lang"])
    delivered = await drain_over_the_wire(pages, "alice")
    assert [change["key"]["path"] for change in delivered["datachanges"]] == ["prefs.lang"]


async def test_every_addressed_exchange_kind_waits_for_the_move(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-1")
    commander.connection_user["sess-1"] = "alice"
    commander.page_connection["p1"] = "sess-1"
    shipped: list[list[str]] = []

    async def collect(buffer: dict[str, list[dict[str, Any]]]) -> None:
        shipped.append(list(buffer))

    commander.flush_exchange = collect  # type: ignore[method-assign]
    commander.moving["alice"] = asyncio.Event()
    addressed = [
        asyncio.create_task(
            commander.route_exchange({"kind": kind, "target": target, "filters": None})
        )
        for kind, target in (
            ("user_store", "alice"),
            ("connection_store", "sess-1"),
            ("page_store", "p1"),
        )
    ]
    await asyncio.sleep(0)
    # A filtered broadcast addresses a set, not a user: it never holds, and it
    # ships against the map as it reads right now.
    await commander.route_exchange({"kind": "page_store", "target": None, "filters": "user:alice"})
    assert shipped == [["W:w-1"]]
    assert not any(task.done() for task in addressed)
    # All three chains reach alice, and all three resolve past the barrier.
    commander.assign_user("alice", "W:w-2")
    commander.release_move("alice")
    await asyncio.gather(*addressed)
    assert shipped[1:] == [["W:w-2"], ["W:w-2"], ["W:w-2"]]


async def test_a_login_arriving_during_a_move_joins_on_the_destination(pool: Any) -> None:
    commander = pool.commander
    reception = str(commander.reception)
    source = other_than(pool, reception)
    tilt_away(commander, reception)
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    assert commander.user_worker_map["alice"] == source
    probe = InstallProbe(commander)
    probe.hold()
    move = asyncio.create_task(commander.move_user("alice", reception))
    await probe.arrived.wait()
    # A second guest logs in as alice while her slice is in the commander's
    # custody: the map still names the source, and a residence read now would
    # install the arriving connection on the worker she has just left.
    await commander.forward_call("sess-2", "/op/new_connection")
    joining = asyncio.create_task(
        commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    )
    await asyncio.sleep(0)
    # The move is still in flight, so the barrier that would hold the join
    # is genuinely open — not merely a join that hasn't been scheduled yet.
    assert "alice" in commander.moving
    probe.release()
    assert await move is True
    await joining
    # Held, not misplaced: the join landed on the worker the move chose, and
    # both connections sit on the one slice.
    assert commander.user_worker_map["alice"] == reception
    assert pool.workers[reception].user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    assert pool.workers[source].user_items.get("alice") is None


async def test_the_quiesce_budget_expiring_leaves_the_user_where_it_is(impatient: Any) -> None:
    commander = impatient.commander
    source = await seed_moving_user(impatient)
    target = other_than(impatient, source)
    # One live call that never closes: the user cannot be taken anywhere.
    commander.open_request(source, "alice", "/op/page_ping")
    assert await commander.move_user("alice", target) is False
    assert commander.user_worker_map["alice"] == source
    assert impatient.workers[source].user_items.get("alice") is not None
    assert impatient.workers[target].user_items.get("alice") is None
    assert "alice" not in commander.moving


async def test_a_call_held_by_an_aborted_move_is_released(impatient: Any) -> None:
    commander = impatient.commander
    source = await seed_moving_user(impatient)
    target = other_than(impatient, source)
    commander.open_request(source, "alice", "/op/page_ping")
    move = asyncio.create_task(commander.move_user("alice", target))
    await until(lambda: "alice" in commander.moving)
    parked = asyncio.create_task(
        commander.forward_call("alice", "/op/page_ping", {"page_id": "p1"})
    )
    await asyncio.sleep(0)
    assert not parked.done()
    assert await move is False
    # The barrier falls on the way out, whatever the outcome was.
    assert (await parked)["page_id"] == "p1"


async def test_a_refused_room_sends_the_slice_back_to_the_source(pages: Any) -> None:
    commander = pages.commander
    source = await seed_moving_user(pages)
    target = other_than(pages, source)
    refusal = RefuseInstall(commander, [target])
    # The parcel is placed, but not where it was asked for: not a drain.
    assert await commander.move_user("alice", target) is False
    assert refusal.destinations == [target, source]
    assert commander.user_worker_map["alice"] == source
    assert pages.workers[source].user_items.get("alice")["store"]["prefs.theme"] == "dark"


async def test_a_room_that_refused_the_slice_is_never_offered_it_twice(pages: Any) -> None:
    commander = pages.commander
    source = await seed_moving_user(pages)
    third = await pages.add_worker()
    target = other_than(pages, source, third)
    refusal = RefuseInstall(commander, [target, source])
    assert await commander.move_user("alice", target) is False
    assert refusal.destinations == [target, source, third]
    assert commander.user_worker_map["alice"] == third
    assert pages.workers[third].user_items.get("alice")["store"]["prefs.theme"] == "dark"


# ----------------------------------------------------------------------
# The beat and the compaction: the pool folding itself away
# ----------------------------------------------------------------------


def test_the_ledger_counts_the_reception_at_its_own_threshold(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    # C = 0.5 + 1.0, O = 0: an idle pool of two has one whole worker to spare.
    assert commander.capacity_headroom() == pytest.approx(1.5)
    load(commander, "W:w-2", 0.9)
    assert commander.capacity_headroom() == pytest.approx(0.6)


def test_a_pool_with_no_active_worker_reports_no_headroom(
    commander: UserStickyCommander,
) -> None:
    assert commander.capacity_headroom() == 0.0


def test_the_excess_is_read_against_each_worker_s_own_threshold(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    load(commander, "W:w-1", 0.6)  # the reception: over its 0.5
    load(commander, "W:w-2", 0.9)  # under the gate: not hot
    load(commander, "W:w-3", 1.4)  # over the gate — its cpu component saturates at 1.0
    assert commander.rebalance_excess() == [
        ("W:w-3", pytest.approx(0.25)),
        ("W:w-1", pytest.approx(0.1)),
    ]


async def test_excess_sends_the_beat_to_the_rebalance_and_nowhere_else(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.9)
    commander.pool_beat()
    assert (commander.rebalancing, commander.compacting) == (True, False)
    await asyncio.sleep(0)


async def test_a_pool_with_nothing_to_shed_is_offered_to_the_compaction(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.4)
    commander.pool_beat()
    assert (commander.rebalancing, commander.compacting) == (False, True)
    await asyncio.sleep(0)


async def test_a_compaction_in_flight_holds_the_beat_off_the_rebalance(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.9)  # excess is there: a free beat would shed
    commander.compacting = True
    commander.pool_beat()
    assert commander.rebalancing is False


async def test_a_rebalance_in_flight_holds_the_beat_off_the_compaction(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.4)  # nothing to shed: a free beat would compact
    commander.rebalancing = True
    commander.pool_beat()
    assert commander.compacting is False


async def test_the_probe_return_is_what_sets_the_beat_going() -> None:
    """The beat's attachment point: a returned probe, not a clock of its own."""
    running = LocalPool()
    await running.start(1)
    try:
        commander = running.commander
        name = running.names[0]
        assert (commander.rebalancing, commander.compacting) == (False, False)
        await commander.probe_worker(name)
        # The archived row is fresh knowledge about the pool, and the pass that
        # reads it was dispatched by the return itself.
        assert commander.worker_roster[name]["occupancy"][-1]["report"]["worker"] == name
        assert (commander.rebalancing, commander.compacting) == (False, True)
        await asyncio.sleep(0)
    finally:
        await running.stop()


async def test_a_worker_sitting_on_a_handover_beyond_the_cycles_is_killed() -> None:
    """The caretaker's second eye (#9): probes answered, handover stale — the kill."""
    running = LocalPool()
    await running.start(1)
    try:
        commander = running.commander
        name = running.names[0]
        killed: list[tuple[str, int]] = []
        commander.signal_worker = lambda worker, sig: killed.append((worker, sig))  # type: ignore[method-assign]
        commander.pending_users[name] = (
            time.time() - commander.max_pending_cycles * commander.probe_interval - 1
        )
        await commander.probe_worker(name)
        assert killed == [(name, signal.SIGKILL)]
        # The verdict pre-empts the archive and the beat: a wedged worker's
        # answer is not fresh knowledge about the pool.
        assert len(commander.worker_roster[name]["occupancy"]) == 0
    finally:
        await running.stop()


async def test_a_fresh_handover_never_trips_the_second_eye() -> None:
    running = LocalPool()
    await running.start(1)
    try:
        commander = running.commander
        name = running.names[0]
        killed: list[tuple[str, int]] = []
        commander.signal_worker = lambda worker, sig: killed.append((worker, sig))  # type: ignore[method-assign]
        commander.pending_users[name] = time.time()
        await commander.probe_worker(name)
        assert killed == []
        # The probe return did its ordinary job: archive and beat.
        assert commander.worker_roster[name]["occupancy"][-1]["report"]["worker"] == name
    finally:
        await running.stop()


async def test_hand_user_to_clears_its_entry_whatever_the_answer(pool: Any) -> None:
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    await seed_live_guest(pool, source)
    await commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    encoded = await commander.evict_for_move("alice", commander.user_worker_map["alice"])
    # The answered handover leaves no residue.
    await commander.hand_user_to(target, "alice", encoded)
    assert "alice" in pool.workers[target].user_items
    assert commander.pending_users == {}
    # The failed one neither: the entry falls with the error.
    with pytest.raises(Exception):
        await commander.hand_user_to("W:ghost", "alice", encoded)
    assert commander.pending_users == {}


async def test_a_rebalance_already_in_flight_is_never_doubled(
    commander: UserStickyCommander,
) -> None:
    spawned = []
    original = commander.spawn_pool_pass

    def record(pass_coroutine: Any) -> Any:
        spawned.append(pass_coroutine)
        return original(pass_coroutine)

    commander.spawn_pool_pass = record  # type: ignore[method-assign]
    enroll(commander, "W:w-1")
    commander.trigger_rebalance()
    commander.trigger_rebalance()
    assert len(spawned) == 1
    await asyncio.sleep(0)
    assert commander.rebalancing is False


async def test_a_pool_pass_that_raises_leaves_its_error_on_the_log(
    commander: UserStickyCommander, caplog: Any
) -> None:
    async def failing_pass() -> None:
        raise RuntimeError("the pass fell over")

    with caplog.at_level("ERROR"):
        task = commander.spawn_pool_pass(failing_pass())
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)
    # Nobody awaits a detached pass in production: without the errback the
    # exception would be retrieved by nobody and the failure would be silent.
    assert "the pass fell over" in caplog.text


async def test_a_compaction_already_in_flight_is_never_doubled(
    commander: UserStickyCommander,
) -> None:
    spawned = []
    original = commander.spawn_pool_pass

    def record(pass_coroutine: Any) -> Any:
        spawned.append(pass_coroutine)
        return original(pass_coroutine)

    commander.spawn_pool_pass = record  # type: ignore[method-assign]
    enroll(commander, "W:w-1")
    commander.trigger_compaction()
    commander.trigger_compaction()
    assert len(spawned) == 1
    await asyncio.sleep(0)
    assert commander.compacting is False


async def test_the_compaction_folds_an_idle_pool_onto_its_reception() -> None:
    running = LocalPool(compaction_margin=0.4)
    await running.start(3)
    commander = running.commander
    reception = str(commander.reception)
    tilt_away(commander, reception)
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    host = commander.user_worker_map["alice"]
    assert host != reception
    load(commander, reception, 0.0)  # the tilt did its job: the ledger reads an idle pool
    try:
        await commander.compact_pass()
        # Down to the floor, and the reception is the survivor: never a candidate.
        assert commander.active_workers == [reception]
        assert commander.user_worker_map["alice"] == reception
        assert running.workers[reception].user_items.get("alice") is not None
    finally:
        await running.stop()


async def test_the_compaction_never_folds_below_the_floor() -> None:
    running = LocalPool(compaction_margin=0.4, min_workers=2)
    await running.start(3)
    commander = running.commander
    for name in commander.active_workers:
        load(commander, name, 0.0)
    try:
        await commander.compact_pass()
        # The ledger would fold the pool onto its reception; min_workers is what
        # stops it, one retire in.
        assert len(commander.active_workers) == 2
        assert commander.capacity_headroom() > commander.compaction_margin
    finally:
        await running.stop()


async def test_a_worker_that_does_not_drain_is_not_retired() -> None:
    running = LocalPool(compaction_margin=0.4, move_quiesce_timeout=0.1)
    await running.start(2)
    commander = running.commander
    reception = str(commander.reception)
    tilt_away(commander, reception)
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    host = str(commander.user_worker_map["alice"])
    load(commander, reception, 0.0)
    # One call that never closes: alice cannot be taken anywhere, so the worker
    # holding her cannot be emptied — and a worker holding state is never retired.
    commander.open_request(host, "alice", "/op/page_ping")
    try:
        await commander.compact_pass()
        assert host in commander.active_workers
        assert commander.user_worker_map["alice"] == host
    finally:
        await running.stop()


# ----------------------------------------------------------------------
# The rebalance: the hot worker shedding what it cannot hold
# ----------------------------------------------------------------------


def memory_hot(commander: UserStickyCommander, name: str, fraction: float) -> None:
    """Seed the worker's window so its MEMORY component reads ``fraction``.

    The decisive case of the ratio space: one component over its target with the
    others nearly idle, so the worker gates high while its load stays low.
    """
    limit = commander.memory_limit_mb or 0
    commander.worker_roster[name]["occupancy"].clear()
    commander.record_occupancy(
        name,
        {
            "cpu": 0.05,
            "rss": int(fraction * limit * 1024 * 1024),
            "reusable": 0,
            "executor": {"busy": 0, "total": 0},
        },
    )


def seed_shed(commander: UserStickyCommander, worker: str, seconds: dict[str, float]) -> None:
    """Put users on ``worker``, each with the service time it spent recently."""
    for user, value in seconds.items():
        commander.assign_user(user, worker)
        commander.count_user_consumption(user, value)


async def two_users_on_one_worker(running: LocalPool) -> tuple[str, str]:
    """Log alice and bob in past a tilted reception; returns their worker and a cool one."""
    commander = running.commander
    reception = str(commander.reception)
    tilt_away(commander, reception)
    for session, user in (("sess-1", "alice"), ("sess-2", "bob")):
        await commander.forward_call(session, "/op/new_connection")
        await commander.forward_call(session, "/op/change_connection_user", {"user": user})
    load(commander, reception, 0.0)  # the tilt did its job: only the shed matters now
    host = str(commander.user_worker_map["alice"])
    assert commander.user_worker_map["bob"] == host
    cool = next(name for name in commander.active_workers if name not in (reception, host))
    return host, cool


def test_a_target_is_only_eligible_while_the_whole_excess_fits_under_the_margin(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    load(commander, "W:w-1", 0.0)
    load(commander, "W:w-2", 0.85)
    load(commander, "W:w-3", 0.5)
    # The ceiling is 0.9: 0.85 + 0.1 is over it, 0.5 + 0.1 is not.
    assert commander.pick_rebalance_target(0.1) == "W:w-3"
    # An excess nobody can take under the margin leaves the pass without a target.
    assert commander.pick_rebalance_target(0.45) is None


def test_the_reception_is_never_a_rebalance_target(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.0)  # the coolest worker there is, and out of the question
    load(commander, "W:w-2", 1.4)  # hot: not a target for its own excess either
    assert commander.pick_rebalance_target(0.25) is None


def test_toward_an_empty_target_the_heaviest_users_go_first(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-2", 1.0)
    seed_shed(commander, "W:w-2", {"alice": 5.0, "bob": 3.0, "carol": 2.0})
    # Weights 0.5 / 0.3 / 0.2: two users cover a budget of 0.6, carol is not needed.
    assert commander.pick_rebalance_users("W:w-2", 0.6, target_empty=True) == ["alice", "bob"]


def test_toward_a_loaded_target_the_lightest_users_go_first(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-2", 1.0)
    seed_shed(commander, "W:w-2", {"alice": 5.0, "bob": 3.0, "carol": 2.0})
    assert commander.pick_rebalance_users("W:w-2", 0.4, target_empty=False) == ["carol", "bob"]


def test_an_idle_user_is_never_shed_onto_a_loaded_target(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-2", 1.0)
    seed_shed(commander, "W:w-2", {"alice": 100.0, "dozer": 0.5})
    # dozer carries 0.5% of the worker, under the 2% floor: the move would buy nothing.
    assert commander.pick_rebalance_users("W:w-2", 0.5, target_empty=False) == ["alice"]
    # The floor is the loaded target's rule alone — an empty one takes whatever comes.
    assert commander.pick_rebalance_users("W:w-2", 1.0, target_empty=True) == ["alice", "dozer"]


def test_a_worker_whose_users_served_nothing_recently_weighs_nothing(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 1.0)
    commander.assign_user("alice", "W:w-1")
    assert commander.rebalance_weights("W:w-1") == {}


def test_a_guest_costs_its_worker_but_is_never_shed(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 1.0)
    commander.assign_user("alice", "W:w-1")
    commander.open_request("W:w-1", "sess-9", "/op/page_ping")  # a guest: a row, no map entry
    commander.count_user_consumption("alice", 1.0)
    commander.count_user_consumption("sess-9", 3.0)
    # The guest's three seconds stay with the worker: alice carries a quarter of it.
    assert commander.rebalance_weights("W:w-1") == {"alice": pytest.approx(0.25)}


async def test_a_memory_hot_worker_sheds_by_weight_until_its_excess_is_covered() -> None:
    running = LocalPool(memory_limit_mb=100)
    commander = running.commander
    await running.start(3)
    try:
        host, cool = await two_users_on_one_worker(running)
        memory_hot(commander, host, 0.9)
        commander.count_user_consumption("alice", 3.0)
        commander.count_user_consumption("bob", 1.0)
        # The decisive case of P2: the gate is over 1.0 while the load reads well
        # under it — the max is what sheds.
        assert commander.evaluator.worker_saturation(host) == pytest.approx(1.125)
        assert commander.evaluator.worker_load(host) < 0.9
        await commander.rebalance_pass()
        # Excess 0.125, and alice's three quarters of 1.125 cover it alone.
        assert commander.user_worker_map["alice"] == cool
        assert commander.user_worker_map["bob"] == host
    finally:
        await running.stop()


async def test_a_hot_worker_with_no_absorber_widens_the_pool(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.target = 2
    load(commander, "W:w-1", 0.4)  # the reception is cool, and never a target
    load(commander, "W:w-2", 1.4)  # the only other worker, and it is the hot one
    await commander.rebalance_pass()
    assert commander.target == 3


async def test_a_hot_pool_at_the_ceiling_widens_no_further(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.target = 2
    commander.max_workers = 2
    load(commander, "W:w-1", 0.4)  # the reception is cool, and never a target
    load(commander, "W:w-2", 1.4)  # hot, with nowhere to shed and no room to grow
    await commander.rebalance_pass()
    assert commander.target == 2


async def test_a_move_that_fails_ends_the_pass_and_retires_nobody() -> None:
    running = LocalPool(memory_limit_mb=100, move_quiesce_timeout=0.1)
    commander = running.commander
    await running.start(3)
    try:
        host, cool = await two_users_on_one_worker(running)
        memory_hot(commander, host, 0.9)
        commander.count_user_consumption("alice", 3.0)
        commander.count_user_consumption("bob", 1.0)
        # One call that never closes: alice is the first pick and she cannot leave.
        commander.open_request(host, "alice", "/op/page_ping")
        await commander.rebalance_pass()
        assert len(commander.active_workers) == 3
        assert commander.user_worker_map["alice"] == host
        # The pass ended on the refusal: bob was next in line and never went.
        assert commander.user_worker_map["bob"] == host
        assert commander.users_on(cool) == set()
    finally:
        await running.stop()


# ----------------------------------------------------------------------
# The recycling: a leaking worker succeeded by a fresh one
# ----------------------------------------------------------------------


class FakeMember:
    """The ``ChannelMember`` surface the callbacks read: just the name."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.pid = 0


class RecyclingPool(LocalPool):
    """A ``LocalPool`` whose spawn attaches an in-process worker instead of forking.

    The recycling needs a successor that really registers, so the fake spawn does
    what a child does — a nascent row now, the REGISTER a beat later — with the
    attach deferred to a task, exactly like the fork's own asynchrony.
    """

    def __init__(self, stillborn: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.stillborn = stillborn
        self.spawned: list[str] = []
        self.attaching: list[asyncio.Task[Any]] = []

    async def start(self, count: int) -> None:
        await super().start(count)
        self.commander.spawn_worker = self.spawn  # type: ignore[method-assign]

    def spawn(self) -> str:
        name = self.commander.next_worker_name()
        self.commander.worker_roster[name] = self.commander.new_roster_row(os.getpid(), None)
        self.spawned.append(name)
        if not self.stillborn:
            self.attaching.append(asyncio.create_task(self.add_worker(name)))
        return name


async def a_user_on_the_pool(running: LocalPool, user: str = "alice") -> str:
    """Log one user in over the wire and answer where it landed."""
    await running.commander.forward_call("sess-1", "/op/new_connection")
    await running.commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": user}
    )
    return str(running.commander.user_worker_map[user])


async def test_the_recycled_worker_hands_its_users_to_its_replacement() -> None:
    running = RecyclingPool()
    await running.start(1)
    commander = running.commander
    commander.target = 1
    source = await a_user_on_the_pool(running)
    try:
        assert await commander.recycle_worker(source) is True
        replacement = running.spawned[0]
        # The user travelled, the successor is the whole pool, and the source is
        # on its way out with the target untouched by either move.
        assert commander.user_worker_map["alice"] == replacement
        assert running.workers[replacement].user_items.get("alice") is not None
        assert commander.active_workers == [replacement]
        assert commander.worker_roster[source]["status"] == "draining"
        assert commander.target == 1
    finally:
        await running.stop()


async def test_a_replacement_that_never_registers_declares_the_pool_sick() -> None:
    running = RecyclingPool(stillborn=True)
    await running.start(1)
    commander = running.commander
    commander.READY_TIMEOUT = 0.1
    source = await a_user_on_the_pool(running)
    try:
        # The sick worker is flagged only after its successor registers: a
        # replacement that never comes leaves it UNTOUCHED, by construction,
        # and the failure is the pool's health condition, not the manoeuvre's.
        assert await commander.recycle_worker(source) is False
        assert commander.worker_roster[source]["status"] == "active"
        assert commander.user_worker_map["alice"] == source
        assert commander.regeneration_failed_at is not None
        # New entries get the signal the infrastructure watches...
        with pytest.raises(HTTPException) as refused:
            commander.worker_for("guest-2")
        assert refused.value.status == 503
        # ...the residents keep being served, and the candidate stays silent.
        assert commander.worker_for("alice") == source
        assert commander.recycle_candidate() is None
    finally:
        await running.stop()


async def test_a_straggler_keeps_the_worker_evacuating_never_active_again() -> None:
    running = RecyclingPool()
    await running.start(1)
    commander = running.commander
    commander.target = 1
    source = await a_user_on_the_pool(running)
    # One call that never closes: alice cannot move NOW — but past the flag
    # there is no way back: the worker stays evacuating with its straggler
    # aboard, serving it, never retired and never active again.
    commander.open_request(source, "alice", "/op/page_ping")
    try:
        assert await commander.recycle_worker(source) is True
        assert commander.worker_roster[source]["status"] == "evacuating"
        assert commander.user_worker_map["alice"] == source
        assert commander.worker_for("alice") == source
    finally:
        await running.stop()


def test_an_evacuating_worker_is_out_of_every_picker(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.worker_roster["W:w-1"]["status"] = "evacuating"
    assert commander.active_workers == ["W:w-2"]
    assert commander.reception == "W:w-2"
    assert commander.decide_worker() == "W:w-2"
    assert commander.pick_compaction_target("W:w-2") is None


def test_a_user_still_resident_on_an_evacuating_worker_is_still_served_there(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-1")
    commander.worker_roster["W:w-1"]["status"] = "evacuating"
    # The map is what routing reads, and only the move rewrites it.
    assert commander.worker_for("alice") == "W:w-1"
    assert commander.worker_for("guest") == "W:w-2"


async def test_a_worker_dying_mid_evacuation_died_a_crash(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-1")
    commander.worker_roster["W:w-1"]["status"] = "evacuating"
    await commander.channel_lost(FakeMember("W:w-1"))
    # The evacuation had not finished: this is a death like any other, and what
    # was still on the worker is gone with it.
    assert commander.worker_roster["W:w-1"]["death"] == "crash"
    assert "alice" not in commander.user_worker_map


async def test_the_drain_takes_the_idle_users_first(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    for user in ("alice", "bob", "carol", "dave"):
        commander.assign_user(user, "W:w-1")
    commander.open_request("W:w-1", "alice", "/op/page_ping")
    commander.open_request("W:w-1", "carol", "/op/page_ping")
    taken: list[str] = []

    async def record(user: str, target: str) -> bool:
        taken.append(user)
        commander.assign_user(user, target)
        return True

    commander.move_user = record  # type: ignore[method-assign]
    assert await commander.drain_worker("W:w-1") is True
    # The two with nothing pending go first, alphabetically inside each tier.
    assert taken == ["bob", "dave", "alice", "carol"]


def test_reconcile_spawns_nothing_while_an_evacuation_is_under_way(
    commander: UserStickyCommander,
) -> None:
    spawned: list[str] = []

    def fake_spawn() -> str:
        return enroll(commander, f"W:new-{len(spawned)}", status="nascent")

    commander.spawn_worker = fake_spawn  # type: ignore[method-assign]
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.target = 2
    spawned.append(commander.spawn_worker())  # the replacement, beyond the target
    commander.worker_roster["W:w-1"]["status"] = "evacuating"
    commander.reconcile()
    # The pass spawned its own replacement: the shortfall math must not add one.
    assert len(spawned) == 1
    assert len(commander.living_workers) == 2


# ----------------------------------------------------------------------
# The recycling trigger: the third force in the beat
# ----------------------------------------------------------------------

MB = 1024 * 1024


def leaking_commander(tmp_path: Any, **kwargs: Any) -> UserStickyCommander:
    """A commander with a memory limit — without one nothing ever recycles."""
    return UserStickyCommander(
        workers=0, path=str(tmp_path / "hub.sock"), memory_limit_mb=1024, **kwargs
    )


def leak(commander: UserStickyCommander, name: str, hours: float | None) -> None:
    """Seed the worker's floor series so its time to limit reads ``hours``.

    Eight floors an hour apart on a straight line: the recent half carries the
    same slope as the whole, so the acceleration corrective changes nothing and
    the reading is the arithmetic below. ``hours=None`` seeds a FLAT series —
    a floor going nowhere, which reads as infinite time.
    """
    velocity = 10 * MB
    series = commander.worker_roster[name]["floors"]
    series.clear()
    limit = commander.memory_limit_mb or 0
    last = limit * MB - (hours or 0) * velocity
    for step in range(8):
        floor = last if hours is None else last - (7 - step) * velocity
        series.append({"ts": 3600.0 * step, "floor": floor})


def test_the_candidate_is_the_worker_closest_to_its_limit(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    leak(commander, "W:w-1", 8.0)
    leak(commander, "W:w-2", 3.0)
    leak(commander, "W:w-3", None)  # flat: not heading anywhere
    assert commander.evaluator.worker_time_to_limit("W:w-3") is None
    assert commander.recycle_candidate() == "W:w-2"


def test_a_worker_beyond_the_horizon_is_nobody_s_candidate(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    leak(commander, "W:w-1", 13.0)
    assert commander.recycle_candidate() is None
    wider = leaking_commander(tmp_path, recycle_horizon_hours=24.0)
    enroll(wider, "W:w-1")
    leak(wider, "W:w-1", 13.0)
    assert wider.recycle_candidate() == "W:w-1"


def test_a_pool_with_no_memory_limit_never_has_a_candidate(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    commander.worker_roster["W:w-1"]["floors"].extend(
        {"ts": 3600.0 * step, "floor": step * MB} for step in range(8)
    )
    assert commander.recycle_candidate() is None


async def test_excess_outranks_a_leak_in_the_beat(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.9)
    leak(commander, "W:w-1", 1.0)  # dying of both: the latency comes first
    commander.pool_beat()
    assert (commander.rebalancing, commander.recycling, commander.compacting) == (
        True,
        False,
        False,
    )
    await asyncio.sleep(0)


async def test_a_leak_outranks_the_compaction_in_the_beat(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.4)  # nothing to shed: a leakless beat would compact
    leak(commander, "W:w-1", 3.0)
    recycled: list[str] = []

    async def fake_recycle(name: str) -> bool:
        recycled.append(name)
        return True

    commander.recycle_worker = fake_recycle  # type: ignore[method-assign]
    commander.pool_beat()
    assert (commander.rebalancing, commander.recycling, commander.compacting) == (
        False,
        True,
        False,
    )
    await asyncio.sleep(0)
    # One worker per pass, and the flag comes down with it.
    assert recycled == ["W:w-1"]
    assert commander.recycling is False


async def test_a_pool_with_no_leak_is_still_offered_to_the_compaction(
    tmp_path: Any,
) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.4)
    leak(commander, "W:w-1", None)
    commander.pool_beat()
    assert (commander.rebalancing, commander.recycling, commander.compacting) == (
        False,
        False,
        True,
    )
    await asyncio.sleep(0)


async def test_a_recycling_in_flight_holds_the_whole_beat_off(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.9)  # excess is there: a free beat would shed
    commander.recycling = True
    commander.pool_beat()
    assert (commander.rebalancing, commander.compacting) == (False, False)


async def test_a_pass_that_finds_no_candidate_left_recycles_nothing(
    tmp_path: Any,
) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    commander.recycling = True
    await commander.recycle_pass()
    assert commander.recycling is False


async def test_the_in_process_worker_is_never_recycled(tmp_path: Any) -> None:
    """The single role's worker IS the commander's process: no successor sheds
    its leak, no retire has a process to end — the candidate skips it and a
    direct recycle refuses it."""
    commander = leaking_commander(tmp_path)
    local = enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.worker = SimpleNamespace(name=local)  # type: ignore[assignment]
    leak(commander, "W:w-1", 2.0)  # the worst leak of the pool, and still skipped
    leak(commander, "W:w-2", 5.0)
    assert commander.recycle_candidate() == "W:w-2"
    with pytest.raises(ValueError, match="in-process"):
        await commander.recycle_worker(local)


async def test_a_stop_mid_recycling_still_retires_the_evacuating_worker(
    commander: UserStickyCommander,
) -> None:
    """``stop()`` walks every non-dead row: an ``evacuating`` worker is outside
    ``living_workers`` but its process is alive and must still be told to exit;
    the tombstones alone have nothing left to end."""
    enroll(commander, "W:w-1", status="evacuating")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3", status="dead")
    await commander.stop()
    statuses = {name: entry["status"] for name, entry in commander.worker_roster.items()}
    assert statuses == {"W:w-1": "draining", "W:w-2": "draining", "W:w-3": "dead"}


async def test_a_source_dying_mid_evacuation_stays_a_buriable_tombstone(
    tmp_path: Any,
) -> None:
    """``channel_lost`` lands inside the moves: neither the step nor the retire
    tail may touch a row it stamped ``dead`` — the tombstone stays buriable."""
    commander = leaking_commander(tmp_path)

    def fake_spawn() -> str:
        return enroll(commander, f"W:new-{len(commander.worker_roster)}")

    commander.spawn_worker = fake_spawn  # type: ignore[method-assign]

    async def die_mid_move(user: str, target: str) -> bool:
        await commander.channel_lost(FakeMember("W:src-1"))
        return False

    enroll(commander, "W:src-1")
    commander.assign_user("alice", "W:src-1")
    commander.move_user = die_mid_move  # type: ignore[method-assign]
    assert await commander.recycle_worker("W:src-1") is True
    row = commander.worker_roster["W:src-1"]
    assert (row["status"], row["death"]) == ("dead", "crash")

    # And the success tail never retires a corpse: a row swept empty by its
    # own death keeps its obituary.
    async def deliver_then_die(user: str, target: str) -> bool:
        commander.assign_user(user, target)
        await commander.channel_lost(FakeMember("W:src-2"))
        return True

    enroll(commander, "W:src-2")
    commander.assign_user("bob", "W:src-2")
    commander.move_user = deliver_then_die  # type: ignore[method-assign]
    assert await commander.recycle_worker("W:src-2") is True
    row = commander.worker_roster["W:src-2"]
    assert (row["status"], row["death"]) == ("dead", "crash")
    commander.bury_workers(time.monotonic() + TOMBSTONE_SECONDS + 10)
    assert "W:src-1" not in commander.worker_roster
    assert "W:src-2" not in commander.worker_roster


async def test_the_evacuating_flag_is_up_while_the_users_move(tmp_path: Any) -> None:
    """The status is not scaffolding: every move of the evacuation finds its
    source flagged — pinned here so removing the flag fails a test."""
    commander = leaking_commander(tmp_path)
    seen: list[str] = []

    def fake_spawn() -> str:
        return enroll(commander, "W:new-1")

    async def record_status(user: str, target: str) -> bool:
        seen.append(commander.worker_roster["W:w-1"]["status"])
        commander.assign_user(user, target)
        return True

    enroll(commander, "W:w-1")
    commander.assign_user("alice", "W:w-1")
    commander.spawn_worker = fake_spawn  # type: ignore[method-assign]
    commander.move_user = record_status  # type: ignore[method-assign]
    assert await commander.recycle_worker("W:w-1") is True
    assert seen == ["evacuating"]
    # Emptied by its own first pass, the source retired itself.
    assert commander.worker_roster["W:w-1"]["status"] == "draining"


async def test_the_wait_aborts_at_once_on_a_replacement_already_dead(
    commander: UserStickyCommander,
) -> None:
    """A replacement stamped dead will never register: the wait must raise now,
    not stare at the tombstone for the whole READY_TIMEOUT (30s)."""
    enroll(commander, "W:corpse", status="dead")
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="died before registering"):
        await commander.wait_worker_ready("W:corpse")
    assert time.monotonic() - started < 1.0


async def test_an_open_evacuation_silences_the_candidate(tmp_path: Any) -> None:
    """One succession at a time: while a worker is evacuating, no new
    recycling opens, however sick another worker reads."""
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    leak(commander, "W:w-1", 2.0)
    assert commander.recycle_candidate() == "W:w-1"
    enroll(commander, "W:evac", status="evacuating")
    assert commander.recycle_candidate() is None


async def test_a_sick_pool_pauses_between_regeneration_probes(tmp_path: Any) -> None:
    """While the pool cannot regenerate, the candidate stays silent — probing
    a broken world every beat would fork one stillborn per beat."""
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    leak(commander, "W:w-1", 2.0)
    commander.regeneration_failed_at = time.monotonic()
    assert commander.recycle_candidate() is None
    # The pause expires: the recycling may probe the world again.
    commander.regeneration_failed_at = time.monotonic() - RECYCLE_RETRY_SECONDS - 1
    assert commander.recycle_candidate() == "W:w-1"


async def test_the_users_own_calls_carry_a_lingering_evacuation_to_its_end(
    tmp_path: Any,
) -> None:
    """A straggler mid-call holds nothing up; the instant his last call closes
    he is carried over — no clock ever needs to find him idle — and the next
    beat buries the emptied worker."""
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1", status="evacuating")
    enroll(commander, "W:w-2")
    commander.worker_roster["W:w-1"]["evacuating_since"] = time.monotonic()
    commander.assign_user("alice", "W:w-1")
    request = commander.open_request("W:w-1", "alice", "/op/page_ping")
    moved: list[str] = []

    async def record(user: str, target: str) -> bool:
        moved.append(user)
        commander.assign_user(user, target)
        return True

    commander.move_user = record  # type: ignore[method-assign]
    commander.pool_beat()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # Mid-call: nothing moved, and the beat's other forces stayed free.
    assert moved == []
    assert commander.worker_roster["W:w-1"]["status"] == "evacuating"
    # His call closes: the move launches THERE, on the spot.
    commander.close_request("W:w-1", "alice", request)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert moved == ["alice"]
    # The next beat closes the books on the emptied worker.
    commander.pool_beat()
    assert commander.worker_roster["W:w-1"]["status"] == "draining"


async def test_a_failed_carry_drops_the_session_loudly(tmp_path: Any) -> None:
    """The one genuinely anomalous situation: a user that cannot be carried
    gets an error, never a silent limbo — the surface forgets him, so his next
    call fails loudly and his next login seats him fresh on a healthy worker."""
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1", status="evacuating")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-1")
    request = commander.open_request("W:w-1", "alice", "/op/page_ping")

    async def refuse(user: str, target: str) -> bool:
        return False

    commander.move_user = refuse  # type: ignore[method-assign]
    commander.close_request("W:w-1", "alice", request)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert "alice" not in commander.user_worker_map
    assert "alice" not in commander.users_on("W:w-1")


def test_an_unmapped_identity_leaves_no_standing_note(
    commander: UserStickyCommander,
) -> None:
    """Anonymous bookkeeping is ephemeral — the legacy dispatcher's own rule:
    a guest's row lives exactly as long as its calls, so no orphan note can
    ever accumulate or hold an evacuation hostage."""
    enroll(commander, "W:w-1")
    request = commander.open_request("W:w-1", "sess-guest", "/op/page_ping")
    assert "sess-guest" in commander.users_on("W:w-1")
    commander.close_request("W:w-1", "sess-guest", request)
    assert "sess-guest" not in commander.users_on("W:w-1")


async def test_a_delivery_toward_a_retired_worker_fails_loudly(
    commander: UserStickyCommander,
) -> None:
    """The accepted rare race (probability-weighted rule): a delivery decided
    an instant before its target stopped serving must END IN AN ERROR — never
    a slice landed on a worker under SIGTERM with the client told success."""
    enroll(commander, "W:w-1", status="draining")
    with pytest.raises(RuntimeError, match="not serving"):
        await commander.hand_user_to("W:w-1", "alice", "blob")


async def test_a_stillborn_already_buried_keeps_its_obituary(tmp_path: Any) -> None:
    """The reconcile can stamp the replacement dead before the wait notices:
    closing the manoeuvre must not flip that tombstone into a draining no
    gravedigger ever collects."""
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")

    def fake_spawn() -> str:
        return enroll(commander, "W:repl", status="dead")

    commander.spawn_worker = fake_spawn  # type: ignore[method-assign]
    assert await commander.recycle_worker("W:w-1") is False
    assert commander.worker_roster["W:repl"]["status"] == "dead"
    assert commander.worker_roster["W:w-1"]["status"] == "active"
    assert commander.regeneration_failed_at is not None


async def test_a_vanished_user_is_nobody_s_move(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    assert await commander.move_user("ghost", "W:w-1") is False


def test_the_503_covers_one_window_and_lapses(tmp_path: Any) -> None:
    """The 503 is the answer of the moment, not a quarantine: Mario turned
    away comes back five minutes later and finds the door open."""
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    commander.regeneration_failed_at = time.monotonic()
    with pytest.raises(HTTPException) as refused:
        commander.worker_for("guest")
    assert refused.value.status == 503
    commander.regeneration_failed_at = time.monotonic() - RECYCLE_RETRY_SECONDS - 1
    assert commander.worker_for("guest") == "W:w-1"


def test_a_claim_in_the_flag_only_window_is_ignored(
    commander: UserStickyCommander,
) -> None:
    """Between the fold raising the flag and place_login's decision the user
    is flagged but unmapped: a foreign claim landing in that window must not
    seat him — the placement in flight owns the decision."""
    enroll(commander, "W:w-1")
    commander.placing.add("alice")
    commander.register_user("alice", "W:w-1")
    assert "alice" not in commander.user_worker_map


async def test_a_resident_join_never_drops_a_flag_it_does_not_own(
    commander: UserStickyCommander,
) -> None:
    """A second login chained onto a placement in flight takes the resident
    branch: its own finally must not release the calls parked on the FIRST
    install, which is still on the wire."""
    enroll(commander, "W:w-1")
    commander.placing.add("alice")
    commander.assign_user("alice", "W:w-1")

    async def deliver(worker: str, user: str, encoded: str) -> Any:
        return {"register_item_id": user}

    commander.hand_user_to = deliver  # type: ignore[method-assign]
    await commander.place_login("alice", "second-blob")
    assert "alice" in commander.placing


def test_a_stalled_evacuation_is_reported(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """The one human-visible output of a non-converging evacuation must
    actually fire: stalled past the pool's own clocks means a warning."""
    enroll(commander, "W:w-1", status="evacuating")
    commander.assign_user("alice", "W:w-1")
    commander.open_request("W:w-1", "alice", "/op/page_ping")
    row = commander.worker_roster["W:w-1"]
    row["evacuating_since"] = time.monotonic() - CONNECTION_MAX_AGE - 10
    with caplog.at_level(logging.WARNING):
        commander.advance_evacuations()
    assert any("stalled" in record.getMessage() for record in caplog.records)


async def test_a_move_waits_out_a_landing_before_reading_the_source(
    commander: UserStickyCommander,
) -> None:
    """A landing user is visible (map written at the decision) but not yet
    movable: the move parks on the flag instead of evicting a slice that has
    not arrived."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.placing.add("alice")
    commander.assign_user("alice", "W:w-1")
    move = asyncio.create_task(commander.move_user("alice", "W:w-2"))
    await asyncio.sleep(0)
    assert "alice" not in commander.moving
    move.cancel()
    with pytest.raises(asyncio.CancelledError):
        await move


async def test_the_compaction_narrows_the_target_it_folds(
    commander: UserStickyCommander,
) -> None:
    """One decrement per fold: folding a worker away WITHOUT lowering the
    target would leave the reconcile respawning it forever."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    commander.target = 3
    commander.compacting = True
    await commander.compact_pass()
    # One fold happened (the margin stops the second): target followed it.
    assert commander.target == 2
    assert len(commander.living_workers) == 2


async def test_a_registered_worker_clears_the_regeneration_condition(
    commander: UserStickyCommander,
) -> None:
    """Any successful REGISTER is the proof the pool regenerates again: the
    condition clears and the new entries are admitted once more."""

    async def no_replica(worker: str) -> None:
        return None

    commander.bootstrap_replica = no_replica  # type: ignore[method-assign]
    commander.regeneration_failed_at = time.monotonic()
    enroll(commander, "W:w-1", status="nascent")
    await commander.member_joined(FakeMember("W:w-1"))
    assert commander.regeneration_failed_at is None


# ----------------------------------------------------------------------
# The same sequence over a real socket and a real child
# ----------------------------------------------------------------------


@pytest.mark.timeout(60)
async def test_the_login_survives_real_children_over_uds() -> None:
    running = UserStickyCommander(
        workers=0,
        worker_kwargs={"max_threads": 2},
    )
    await running.start()
    try:
        running.scale(2)
        await running.wait_workers_ready(2)
        source = running.reception
        target = next(name for name in running.active_workers if name != source)
        tilt_away(running, source)
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
