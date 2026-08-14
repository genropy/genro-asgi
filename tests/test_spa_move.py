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

"""Reception, sticky routing, the login that stays — and the move it orders.

The pool here is real but in-process: two ``UserStickyWorker`` attached to the
commander's own hub over ``LocalChannel`` pairs, so every frame still crosses
encode/decode and the settlement happens over ordinary CALLs — only the fork is
missing. One subprocess smoke at the end proves the same sequence survives a
real socket and a real child.

The login itself never ships (ratified 2026-08-12): the fold maps the user to
the worker it logged in on and the response leaves at once. What the decision
calls for — a move toward the worker the user belongs on, the discard of a
remnant left by a login onto a user resident elsewhere — runs DETACHED, so the
tests below wait it out with ``settled_at`` instead of reading the map straight
after the call.

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
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_routes import route

from genro_tytx import from_tytx, to_tytx

from genro_asgi.channel.local import LocalChannel
from genro_asgi.exceptions import HTTPException
from genro_asgi.spa.commander import (
    COMPACTION_MARGIN,
    EVACUATION_WARN_INTERVAL,
    FREEZE_IDLE_AFTER,
    FROZEN,
    FROZEN_GUEST_LIFETIME,
    FROZEN_USER_LIFETIME,
    SPAWN_MARGIN,
    TOMBSTONE_SECONDS,
    UserStickyCommander,
)
from genro_asgi.spa.register_registry import GUEST_PREFIX
from tests.storage_support import site_storage
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


async def settled_at(commander: UserStickyCommander, user: str, worker: str) -> None:
    """Wait out the settlement a login detached: the user is on ``worker``, at rest.

    The response comes back before the transfer, so every assertion about where
    a user ENDED UP goes through here — the map naming the destination and no
    hold of that user still standing.
    """
    await until(
        lambda: commander.user_worker_map.get(user) == worker and not commander.is_held(user)
    )


class InstallProbe:
    """Sit on the handover CALL: hold it, or answer it with an error.

    Everything else goes straight through to the real hub, so the rest of the
    flow is untouched — this only makes the window in which the move's hold is
    up wide enough to observe, and the install failure deterministic.
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


def test_with_no_active_worker_a_ready_pool_says_so_loudly(
    commander: UserStickyCommander,
) -> None:
    """A pool that answers requests always has a worker to answer them with, so
    a ``ready`` pool with no receiver is an impossible state and raises. The 503
    belongs to the one condition where the emptiness is expected — a
    ``restricted`` pool, which the test below drives."""
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


def a_login_batch(session_id: str = "sess-1") -> list[dict[str, Any]]:
    """The two events a guest's first login rides up with."""
    return [
        {"op": "new_user", "seq": 1, "user": session_id},
        {
            "op": "change_connection_user",
            "seq": 2,
            "user": "alice",
            "previous_user": session_id,
            "session_id": session_id,
        },
    ]


def test_a_login_maps_the_user_to_the_worker_it_was_born_on(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    commander.place_logins("W:w-1", a_login_batch())
    # The map is written at the decision, and the fold's decision is "the user
    # lives where it logged in": nothing travels, nothing is held.
    assert commander.user_worker_map == {"alice": "W:w-1"}
    assert commander.users_on("W:w-1") == {"alice"}
    assert commander.is_held("alice") is False


def test_the_prior_residence_is_read_before_the_login_is_folded(
    commander: UserStickyCommander,
) -> None:
    """``prior`` is where the map pointed BEFORE the fold, and the fold is what
    changes it: read afterwards, a first login would look like a resident one."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    seen: list[str | None] = []

    def spying(worker: str, user: str, session_id: str, prior: str | None) -> None:
        seen.append(prior)

    commander.settle_login = spying  # type: ignore[method-assign]
    commander.place_logins("W:w-1", a_login_batch())
    assert seen == [None]
    # The fold ran all the same: alice is on the surface, at her birthplace.
    assert commander.user_worker_map == {"alice": "W:w-1"}
    # A second login of the same user, announced elsewhere, reads the residence.
    commander.place_logins("W:w-2", a_login_batch("sess-2"))
    assert seen == [None, "W:w-1"]


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


def test_a_login_is_on_the_surface_from_the_fold(commander: UserStickyCommander) -> None:
    """The map is written at the DECISION, and for a login that is the fold: from
    that instant no reader can miss the user — no emptiness verdict, no late
    claim from another worker — and no sweep spares it either."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.place_logins("W:w-1", a_login_batch())
    assert "alice" in commander.users_on("W:w-1")
    assert commander.user_worker_map["alice"] == "W:w-1"
    # A claim from another worker never re-points a user somebody holds.
    commander.register_user("alice", "W:w-2")
    assert commander.user_worker_map["alice"] == "W:w-1"
    # And the sweep of a dead worker condemns every user of the row: since the
    # login stopped shipping there is nobody left to exempt.
    assert commander.sweep_worker("W:w-1") == ["alice"]
    assert "alice" not in commander.user_worker_map


async def test_a_waiter_that_wakes_into_a_second_move_parks_again(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.moving["alice"] = asyncio.Event()
    parked = asyncio.create_task(commander.resolve_worker("alice"))
    await asyncio.sleep(0)
    # The first move lands and a second one is raised before the waiter is
    # scheduled: the hold is re-read on every wakeup, so it parks again instead
    # of resolving against a map that is provisional once more.
    commander.assign_user("alice", "W:w-1")
    commander.release_move("alice")
    commander.moving["alice"] = asyncio.Event()
    await asyncio.sleep(0)
    assert not parked.done()
    # It resolves to the worker the last move carried the user to.
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
# The login over two in-process workers: it stays, then the move carries it
# ----------------------------------------------------------------------


async def test_a_guest_call_lands_on_the_reception(pool: Any) -> None:
    reception = pool.commander.reception
    entry = await pool.commander.forward_call("sess-1", "/op/new_user")
    assert entry["register_item_id"] == "sess-1"
    assert pool.commander.user_worker_map == {"sess-1": reception}
    assert pool.workers[reception].user_items.get("sess-1") is not None


async def test_the_login_returns_before_the_move_it_ordered(pool: Any) -> None:
    source = pool.commander.reception
    target = next(name for name in pool.names if name != source)
    tilt_away(pool.commander, source)
    await pool.commander.forward_call("sess-1", "/op/new_connection")
    entry = await pool.commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    # Everything here is true AT RETURN TIME: the guest is told its number while
    # its slice is still on the worker it logged in on, transfer or no transfer.
    assert entry["register_item_id"] == "alice"
    assert pool.commander.user_worker_map["alice"] == source
    assert pool.workers[source].user_items.get("alice")["tag"] == "carried"
    # Only then does the detached move carry it where it belongs.
    await settled_at(pool.commander, "alice", target)
    assert pool.workers[target].user_items.get("alice")["tag"] == "carried"
    assert pool.workers[source].user_items.get("alice") is None
    assert pool.workers[source].user_items.get("sess-1") is None


async def test_a_login_that_belongs_where_it_was_born_never_travels(pool: Any) -> None:
    source = pool.commander.reception
    other = next(name for name in pool.names if name != source)
    pool.commander.assign_user("ballast", other)
    probe = InstallProbe(pool.commander)
    await pool.commander.forward_call("sess-1", "/op/new_connection")
    await pool.commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    # The reception is under its threshold, so alice belongs where she is: the
    # settle orders nothing and no handover is ever issued.
    assert pool.commander.user_worker_map["alice"] == source
    assert pool.workers[source].user_items.get("alice")["tag"] == "carried"
    assert probe.destinations == []


async def test_a_call_issued_during_the_login_move_waits_for_the_room(pool: Any) -> None:
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    tilt_away(commander, source)
    probe = InstallProbe(commander)
    probe.hold()
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    await probe.arrived.wait()
    # Mid-install of the detached move: the map still names the source, and the
    # move's own hold is what keeps alice's calls parked.
    assert commander.user_worker_map["alice"] == source
    assert "alice" in commander.moving
    parked = asyncio.create_task(commander.forward_call("alice", "/op/drop_user"))
    await asyncio.sleep(0)
    assert not parked.done()
    probe.release()
    dropped = await parked
    # It was served by the destination, on the entry the parcel carried.
    assert dropped["tag"] == "carried"
    assert probe.destinations == [target]
    assert "alice" not in commander.user_worker_map


async def test_a_source_swept_mid_move_never_half_resurrects_the_user(
    pool: Any, caplog: Any
) -> None:
    """A source dying while the parcel is in custody takes the user with it.

    The switch never re-writes the map over the rows the sweep demolished — a
    map entry pointing at real pages with no surface rows under it would drop
    every cross-worker delivery in silence. The slice is discarded where it
    landed, loudly, and the user is exactly as dead as if no move had been in
    flight.
    """
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    tilt_away(commander, source)
    probe = InstallProbe(commander)
    probe.hold()
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await probe.arrived.wait()
    # The source dies with the parcel in custody: the sweep takes alice off the
    # surface, rows and map together.
    await commander.channel_lost(FakeMember(source))
    assert "alice" not in commander.user_worker_map
    with caplog.at_level(logging.WARNING):
        probe.release()
        await until(lambda: not commander.is_held("alice"))
        await until(lambda: "alice" not in pool.workers[target].user_items)
    assert "alice" not in commander.user_worker_map
    assert "swept mid-move" in caplog.text
    assert "alice" not in commander.user_connections


async def test_the_rehome_materializes_at_the_residence_of_the_moment(
    commander: UserStickyCommander,
) -> None:
    """The map is re-read after the evict: a move that landed meanwhile must
    send the arriving connection to where the user lives NOW, never to the
    worker the slice has just left."""
    for name in ("W:a", "W:b", "W:c"):
        enroll(commander, name)
    commander.assign_user("alice", "W:b")
    calls: list[tuple[str, str]] = []

    async def scripted_call(
        name: str, path: str, data: Any = None, timeout: float | None = None
    ) -> Any:
        calls.append((name, path))
        if path.endswith("evict_user"):
            # A move lands while the rehome is parked on this very CALL.
            commander.assign_user("alice", "W:c")
            return {"events": [], "result": {"encoded": "x"}}
        return {"events": [], "result": {}}

    commander.hub.call = scripted_call  # type: ignore[method-assign]
    await commander.rehome_login("W:a", "alice", "sess-2", [])
    assert calls == [
        ("W:a", "/op/evict_user"),
        ("W:c", "/op/new_connection"),
    ]


async def test_a_join_answered_to_a_commanded_move_is_loud(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """A commanded move never expects a resident at its destination: an install
    that JOINED means somebody re-keyed onto it first and the parcel's own
    entry and store yielded — accepted, but never mute."""
    enroll(commander, "W:d")

    async def joining_call(
        name: str, path: str, data: Any = None, timeout: float | None = None
    ) -> Any:
        return {"events": [], "result": {"user": "alice", "joined": True}}

    commander.hub.call = joining_call  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING):
        landed = await commander.install_in_custody("alice", "W:d", "blob")
    assert landed == "W:d"
    assert "JOINED a resident" in caplog.text


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
    # The anonymous page declares its guest-named user, as the legacy bridge does.
    await pool.commander.forward_call(
        "guest_sess-1", "/op/new_page", {"page_id": page_id, "session_id": "sess-1"}
    )
    worker = pool.workers[source]
    worker.registry.subscribe_store_path(page_id, "prefs")
    worker.setStoreSubscription("sess-1", page_id=page_id, storename="page", prefix="counter")
    await pool.commander.forward_call(
        "sess-1", "/op/subscribeTable", {"table": "orders", "page_id": page_id}
    )
    page = worker.page_items.get(page_id)
    page["store"]["counter"] = 1
    worker.user_items.get("guest_sess-1")["store"]["prefs.theme"] = "dark"
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
    await settled_at(pages.commander, "alice", target)
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
    await settled_at(pages.commander, "alice", target)
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
    await settled_at(pages.commander, "alice", target)
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
    await settled_at(pages.commander, "alice", target)
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
    await settled_at(pages.commander, "alice", target)

    arrived = pages.workers[target].connection_items.get("sess-1")
    assert arrived["store"]["device.width"] == 1280
    assert pages.workers[source].connection_items.get("sess-1") is None


async def test_a_dbevent_notified_after_the_move_reaches_the_moved_page(pages: Any) -> None:
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(pages.commander, source)
    await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await settled_at(pages.commander, "alice", target)
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


async def test_the_commanded_eviction_carries_the_whole_live_slice(pages: Any) -> None:
    """``evict_user`` on order is the ONE road out, and it rebuilds the slice whole."""
    source = pages.commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(pages.commander, source)
    seeded = await seed_live_guest(pages, source)
    await pages.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await settled_at(pages.commander, "alice", target)

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
    # Nothing pending was lost on the way: the two changes and the deposit the
    # move carried are still what the page reads at the arrival.
    delivered = await drain_over_the_wire(pages, "alice")
    assert [change["key"]["path"] for change in delivered["datachanges"]] == [
        change["key"]["path"] for change in seeded["datachanges"]
    ]
    assert delivered["dbevents"] == [seeded["deposit"]]


async def test_a_refused_room_leaves_the_login_and_its_baggage_at_home(pages: Any) -> None:
    """The login's transfer is the ordinary move, failure path included: a room
    that refuses the parcel sends it back where the user logged in, and the
    response the client already holds stays true."""
    commander = pages.commander
    source = commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(commander, source)
    seeded = await seed_live_guest(pages, source)
    refusal = RefuseInstall(commander, [target])
    entry = await commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    assert entry["tag"] == "carried"
    # The parcel was offered the room it belongs in, refused, and salvaged home.
    await until(lambda: refusal.destinations == [target, source])
    await settled_at(commander, "alice", source)
    assert commander.user_worker_map["alice"] == source
    worker = pages.workers[source]
    assert worker.user_items.get("alice")["tag"] == "carried"
    assert worker.page_items.get("p1") is not None
    assert worker.subscriptions.pages_for("orders") == {"p1"}
    # And nothing pending was lost in the round trip.
    delivered = await drain_over_the_wire(pages, "alice")
    assert [change["key"]["path"] for change in delivered["datachanges"]] == [
        change["key"]["path"] for change in seeded["datachanges"]
    ]


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


async def test_a_login_onto_a_user_resident_elsewhere_discards_the_remnant(
    pages: Any,
) -> None:
    """The declared boundary of guest-carry: the resident WINS. The arriving
    connection is materialized at the residence and the remnant the login left
    on the announcing worker — the guest's entry, its pages, its parcel — dies
    there, loudly and not silently."""
    commander = pages.commander
    source = commander.reception
    target = next(name for name in pages.names if name != source)
    tilt_away(commander, source)
    await commander.forward_call(
        "sess-1", "/op/new_page", {"page_id": "p1", "session_id": "sess-1"}
    )
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await settled_at(commander, "alice", target)
    resident = pages.workers[target]
    resident.user_items.get("alice")["store"]["prefs.theme"] = "dark"
    # A second guest, on the reception, does some work and logs in as the same user.
    await commander.forward_call(
        "sess-2", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"}
    )
    pages.workers[source].page_items.get("p2")["store"]["counter"] = 1
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    await until(lambda: resident.connection_items.get("sess-2") is not None)

    # Alice never moved and her store is the one that was already open here.
    assert commander.user_worker_map["alice"] == target
    assert resident.user_items.get("alice")["store"]["prefs.theme"] == "dark"
    assert resident.user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    # The reception kept nothing of the guest: entry, page and surface rows gone.
    assert pages.workers[source].user_items.get("alice") is None
    assert pages.workers[source].page_items.get("p2") is None
    assert "p2" not in commander.page_connection
    assert commander.pages_of_connection("sess-2") == []
    # And the connection that survives is served at the residence.
    assert commander.page_worker("p1") == target


async def test_a_failed_remnant_eviction_leaves_the_resident_alone(pool: Any) -> None:
    """The rehome's discard is best effort: an evict that fails is logged and the
    residence is joined anyway — the resident's own slice is never at risk."""
    commander = pool.commander
    source = commander.reception
    target = next(name for name in pool.names if name != source)
    tilt_away(commander, source)
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice", "tag": "carried"}
    )
    await settled_at(commander, "alice", target)
    hub_call = commander.hub.call

    async def refusing(
        name: str, path: str, data: Any = None, timeout: float | None = None
    ) -> Any:
        if path.endswith("evict_user"):
            return {"events": [], "error": "evict refused"}
        return await hub_call(name, path, data, timeout=timeout)

    commander.hub.call = refusing  # type: ignore[method-assign]
    await commander.forward_call("sess-2", "/op/new_connection")
    # The login itself never fails: the discard is somebody else's task.
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    await until(lambda: pool.workers[target].connection_items.get("sess-2") is not None)
    assert commander.user_worker_map["alice"] == target
    assert pool.workers[target].user_items.get("alice")["tag"] == "carried"
    assert pool.workers[target].user_items.get("alice")["connections"] == {"sess-1", "sess-2"}


async def test_only_a_first_login_is_a_free_choice(pool: Any) -> None:
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
    # Nobody held alice: where she BELONGS was decided by load, and the move ran.
    assert decided == [target]
    await settled_at(commander, "alice", target)
    await commander.forward_call("sess-2", "/op/new_connection")
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    await until(lambda: pool.workers[target].connection_items.get("sess-2") is not None)
    # The second connection of a resident user never asks — presence comes first.
    assert decided == [target]
    assert commander.user_worker_map["alice"] == target


# ----------------------------------------------------------------------
# The resident login: the worker already hosts the user, so nothing travels
# ----------------------------------------------------------------------


def spy_on_folded(commander: UserStickyCommander) -> list[dict[str, Any]]:
    """Record every event the commander folds — what the REPLYs carried up."""
    seen: list[dict[str, Any]] = []
    original = commander.place_logins

    def spying(worker: str, events: list[dict[str, Any]]) -> None:
        seen.extend(events)
        original(worker, events)

    commander.place_logins = spying  # type: ignore[method-assign]
    return seen


async def home_bound_alice(pages: Any) -> str:
    """Alice logged in on the reception and belonging there, with page p1 alive.

    Ballast on the other worker makes the reception the least loaded one, so the
    first login belongs where it was born and nothing is detached — and the next
    guest, which the reception also holds, will log in AT HOME.
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
    # The login went up with no baggage: the op does not package, ever.
    logins = [event for event in folded if event["op"] == "change_connection_user"]
    assert [event["session_id"] for event in logins] == ["sess-2"]
    assert "encoded" not in logins[0]
    # And both pages are served afterwards, each on its own connection.
    for page_id in ("p1", "p2"):
        await drain_over_the_wire(pages, "alice", page_id)


async def test_no_login_at_home_installs_anything(pages: Any) -> None:
    commander = pages.commander
    probe = InstallProbe(commander)
    await home_bound_alice(pages)
    # The first login belonged where it was born: no move, so no handover.
    assert probe.destinations == []
    await commander.forward_call(
        "sess-2", "/op/new_page", {"page_id": "p2", "session_id": "sess-2"}
    )
    await commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    # And the resident login had nothing to settle either.
    assert probe.destinations == []


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
    await settled_at(commander, "alice", target)
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


async def test_the_first_connection_is_served_across_the_second_login(pages: Any) -> None:
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
    await settled_at(commander, "alice", target)
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
    await until(lambda: pages.workers[target].connection_items.get("sess-2") is not None)

    # The resident won: alice never moved and both connections are hers. p2 died
    # with the remnant on the reception — the guest's baggage does not travel.
    assert commander.user_worker_map["alice"] == target
    assert pages.workers[target].user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    assert pages.workers[target].page_items.get("p2") is None
    assert "p2" not in commander.page_connection
    await drain_over_the_wire(pages, "alice", "p1")
    await commander.forward_call(
        "alice",
        "/op/set_datachange",
        {
            "change": to_tytx(a_change("prefs.lang", "it"), "json"),
            "kind": "user_store",
            "target": "alice",
        },
    )
    # ONE change, not two: the store p1 keeps watching is the resident one, and
    # the ``prefs`` node was already in it — no fresh Bag was put in its place.
    delivered = await drain_over_the_wire(pages, "alice", "p1")
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
    await settled_at(commander, "alice", source)
    probe = InstallProbe(commander)
    probe.hold()
    move = asyncio.create_task(commander.move_user("alice", reception))
    await probe.arrived.wait()
    # A second guest logs in as alice, ON THE MOVE'S DESTINATION, while her
    # slice is in the commander's custody. The map still names the source, so
    # the fold reads a user resident elsewhere and detaches a rehome.
    await commander.forward_call("sess-2", "/op/new_connection")
    joining = asyncio.create_task(
        commander.forward_call("sess-2", "/op/change_connection_user", {"user": "alice"})
    )
    await asyncio.sleep(0)
    # The move is genuinely still in flight, not merely unscheduled.
    assert "alice" in commander.moving
    probe.release()
    assert await move is True
    await joining
    # The rehome waits the move out and re-reads the map: the residence is now
    # the very worker that announced the login, so there is nothing to discard —
    # the two halves already met there, and both connections sit on one slice.
    for _ in range(5):
        await asyncio.sleep(0)
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


async def test_excess_puts_the_rebalance_first_in_the_plan(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.9)
    assert commander.build_plan()[0] == {"op": "rebalance"}


async def test_a_pool_with_nothing_to_shed_plans_no_rebalance(tmp_path: Any) -> None:
    roomy = UserStickyCommander(
        workers=0, path=str(tmp_path / "hub.sock"), compaction_margin=0.4, spawn_margin=0.2
    )
    for name in ("W:w-1", "W:w-2", "W:w-3"):
        enroll(roomy, name)
    load(roomy, "W:w-1", 0.4)
    plan = roomy.build_plan()
    assert plan  # the compaction has something to do
    assert not [step for step in plan if step["op"] == "rebalance"]


async def test_a_plan_in_flight_builds_no_second_plan(
    commander: UserStickyCommander,
) -> None:
    """The three flags collapsed into one state: a tick landing mid-plan does
    nothing, whatever the pool reads."""
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.9)  # excess is there: a free build would shed
    commander.active_plan = [{"op": "rebalance"}]
    assert commander.build_plan() == []


async def test_the_planner_tick_runs_the_plan_it_builds(
    commander: UserStickyCommander,
) -> None:
    """The task IS the executor: the plan its reading calls for is awaited here."""
    executed: list[list[dict[str, Any]]] = []

    async def record(plan: list[dict[str, Any]]) -> None:
        executed.append(plan)

    commander.execute_plan = record  # type: ignore[method-assign]
    commander.decision_interval = 0.01
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.9)
    ticking = asyncio.create_task(commander.planner())
    try:
        await asyncio.sleep(0.05)
    finally:
        ticking.cancel()
    assert executed == [[{"op": "rebalance"}]]


async def test_a_tick_that_falls_over_leaves_the_clock_running(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """A pool whose shape stopped being decided at all would go unnoticed: the
    failure is logged and the next tick reads the world again."""
    attempts: list[str] = []

    async def falling_over(plan: list[dict[str, Any]]) -> None:
        attempts.append("tick")
        commander.active_plan = None
        raise RuntimeError("the step fell over")

    commander.execute_plan = falling_over  # type: ignore[method-assign]
    commander.decision_interval = 0.01
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.9)
    with caplog.at_level("ERROR"):
        ticking = asyncio.create_task(commander.planner())
        try:
            await asyncio.sleep(0.05)
        finally:
            ticking.cancel()
    assert len(attempts) > 1
    assert "the step fell over" in caplog.text


async def test_the_probe_return_decides_no_shape() -> None:
    """Health only (R1): the probe archives its numbers and pulls no move behind
    itself — the pool is read whole by the planner, on its own clock."""
    running = LocalPool()
    await running.start(1)
    try:
        commander = running.commander
        name = running.names[0]
        built: list[list[dict[str, Any]]] = []
        original = commander.build_plan

        def record() -> list[dict[str, Any]]:
            plan = original()
            built.append(plan)
            return plan

        commander.build_plan = record  # type: ignore[method-assign]
        await commander.probe_worker(name)
        assert commander.worker_roster[name]["occupancy"][-1]["report"]["worker"] == name
        assert built == []
        assert commander.active_plan is None
    finally:
        await running.stop()


async def test_the_planner_lives_and_dies_with_the_commander() -> None:
    """Started in start(), cancelled in stop(): the same discipline as the reconcile."""
    running = LocalPool(decision_interval=0.01)
    await running.start(1)
    try:
        task = running.commander._planner_task
        assert task is not None and not task.done()
    finally:
        await running.stop()
    assert task.cancelled()
    assert running.commander._planner_task is None


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


async def test_deliveries_toward_one_worker_queue_on_its_removalist() -> None:
    """One delivery at a time per destination (#15): the burst serializes.

    An evacuation's call-close moves all aim at one compaction target: launched
    together, only the first leaves — the queued one never appears in
    ``pending_users`` (queueing is not "sitting on a delivery") — and the
    second departs only once the first has answered.
    """
    running = LocalPool()
    await running.start(1)
    try:
        commander = running.commander
        target = running.names[0]
        gate = asyncio.Event()
        order: list[tuple[str, str]] = []

        async def gated_call(
            worker: str, path: str, payload: Any, timeout: Any = None
        ) -> dict[str, Any]:
            order.append(("start", payload["identity"]))
            await gate.wait()
            order.append(("end", payload["identity"]))
            return {"result": "installed"}

        commander.hub.call = gated_call  # type: ignore[method-assign]
        first = asyncio.ensure_future(commander.hand_user_to(target, "anna", "blob-a"))
        second = asyncio.ensure_future(commander.hand_user_to(target, "bruno", "blob-b"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert order == [("start", "anna")]
        assert target in commander.pending_users
        gate.set()
        assert await first == "installed"
        assert await second == "installed"
        assert order == [
            ("start", "anna"),
            ("end", "anna"),
            ("start", "bruno"),
            ("end", "bruno"),
        ]
        assert commander.pending_users == {}
    finally:
        await running.stop()


async def test_a_queued_delivery_reads_the_destinations_current_status() -> None:
    """The serving guard runs AFTER the queue (#15): a mid-queue death is loud.

    The destination stops serving while the second delivery waits its turn:
    the first CALL had already left and completes, the queued one re-reads the
    roster and errors instead of landing a slice on a dead worker.
    """
    running = LocalPool()
    await running.start(1)
    try:
        commander = running.commander
        target = running.names[0]
        gate = asyncio.Event()

        async def gated_call(
            worker: str, path: str, payload: Any, timeout: Any = None
        ) -> dict[str, Any]:
            await gate.wait()
            return {"result": "installed"}

        commander.hub.call = gated_call  # type: ignore[method-assign]
        first = asyncio.ensure_future(commander.hand_user_to(target, "anna", "blob-a"))
        second = asyncio.ensure_future(commander.hand_user_to(target, "bruno", "blob-b"))
        await asyncio.sleep(0)
        commander.worker_roster[target]["status"] = "dead"
        gate.set()
        assert await first == "installed"
        with pytest.raises(RuntimeError, match="not serving"):
            await second
    finally:
        await running.stop()


async def test_two_builds_in_the_same_breath_yield_one_plan(
    commander: UserStickyCommander,
) -> None:
    """The claim is taken by the build itself, in the same synchronous breath as
    the reading: whoever reads the pool second finds it already committed."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.9)
    assert commander.build_plan() == [{"op": "rebalance"}]
    assert commander.build_plan() == []


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


async def test_the_plan_releases_its_claim_even_when_a_step_falls_over(
    commander: UserStickyCommander,
) -> None:
    """A step that raises ends the whole plan — and must not leave the pool
    committed forever: the next tick has to be able to decide again."""

    async def failing_rebalance(now: float | None = None) -> None:
        raise RuntimeError("the step fell over")

    commander.rebalance_pass = failing_rebalance  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await commander.execute_plan([{"op": "rebalance"}])
    assert commander.active_plan is None


async def test_a_condemnation_without_a_replacement_narrows_the_pool(tmp_path: Any) -> None:
    """The ``spawn=False`` branch, executed: no new process, the users leave, and
    the target follows the worker out — or the reconcile would spawn back the
    very process the weight gate said was not needed."""
    commander = leaking_commander(tmp_path, compaction_margin=0.4, spawn_margin=0.2)
    for name in ("W:w-1", "W:w-2", "W:w-3"):
        enroll(commander, name)
    commander.target = 3
    commander.assign_user("alice", "W:w-2")
    spawned: list[str] = []

    def never_spawn() -> str:
        spawned.append("W:unwanted")
        return "W:unwanted"

    commander.spawn_worker = never_spawn  # type: ignore[method-assign]

    async def record(user: str, target: str) -> bool:
        commander.assign_user(user, target)
        return True

    commander.move_user = record  # type: ignore[method-assign]
    await commander.execute_plan([{"op": "replace", "worker": "W:w-2", "spawn": False}])
    assert spawned == []
    assert commander.target == 2
    assert commander.user_worker_map["alice"] != "W:w-2"
    # Emptied by its own evacuation, the source retired itself.
    assert commander.worker_roster["W:w-2"]["status"] == "draining"


async def fold(commander: UserStickyCommander) -> None:
    """Run only the compaction steps of the plan the pool now calls for."""
    plan = commander.build_plan()
    await commander.execute_plan([step for step in plan if step["op"] == "compact"])


async def test_the_compaction_folds_an_idle_pool_onto_its_reception() -> None:
    running = LocalPool(compaction_margin=0.4, spawn_margin=0.2)
    await running.start(3)
    commander = running.commander
    reception = str(commander.reception)
    tilt_away(commander, reception)
    await commander.forward_call("sess-1", "/op/new_connection")
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    # The login's own move takes her off the tilted reception.
    await until(
        lambda: commander.user_worker_map["alice"] != reception
        and not commander.is_held("alice")
    )
    load(commander, reception, 0.0)  # the tilt did its job: the ledger reads an idle pool
    try:
        await fold(commander)
        # Down to the floor, and the reception is the survivor: never a candidate.
        assert commander.active_workers == [reception]
        assert commander.user_worker_map["alice"] == reception
        assert running.workers[reception].user_items.get("alice") is not None
    finally:
        await running.stop()


async def test_the_compaction_stops_where_the_capacity_rule_says() -> None:
    running = LocalPool(compaction_margin=0.6, spawn_margin=0.2)
    await running.start(3)
    commander = running.commander
    for name in commander.active_workers:
        load(commander, name, 0.0)
    try:
        await fold(commander)
        # Three idle workers hold 2.5 of capacity: the first fold leaves 1.5, the
        # second would leave 0.5 — under the margin, so it never happens.
        assert len(commander.active_workers) == 2
        survivor = commander.active_workers[1]
        assert commander.capacity_headroom(exclude=survivor) < commander.compaction_margin
    finally:
        await running.stop()


async def test_a_worker_that_does_not_drain_is_not_retired(tmp_path: Any, caplog: Any) -> None:
    """The fold NAMES the worker holding the user, and the drain refuses to carry
    her: the fold is skipped and reported, the worker keeps its resident, and the
    steps after it still run. The plan is built here, not hand-written, so the
    step really is the one the pool asked for."""
    commander = UserStickyCommander(
        workers=0, path=str(tmp_path / "hub.sock"), compaction_margin=0.3, spawn_margin=0.2
    )
    for name in ("W:w-1", "W:w-2", "W:w-3"):
        enroll(commander, name)
    commander.target = 3
    commander.assign_user("alice", "W:w-2")

    async def refuse(user: str, target: str) -> bool:
        return False  # alice is held: nobody can take her anywhere

    commander.move_user = refuse  # type: ignore[method-assign]
    plan = commander.build_plan()
    folding = [step["worker"] for step in plan if step["op"] == "compact"]
    assert folding == ["W:w-3", "W:w-2"]  # the empty one first, then alice's host
    with caplog.at_level(logging.WARNING):
        await commander.execute_plan(plan)
    assert "worker W:w-2 did not drain" in caplog.text
    assert "W:w-2" in commander.active_workers
    assert commander.user_worker_map["alice"] == "W:w-2"
    # The empty worker ahead of it folded all the same: a refused drain is a fact
    # about ONE worker, not the end of the plan.
    assert "W:w-3" not in commander.active_workers


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
        # Each login's own move has to land before the next one is decided.
        await until(
            lambda user=user: commander.user_worker_map[user] != reception
            and not commander.is_held(user)
        )
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


def test_a_user_already_being_carried_is_never_picked_to_shed(
    commander: UserStickyCommander,
) -> None:
    """A hold up means somebody else is moving that user: picking it would buy a
    refused move and end the pass, so the next-heaviest goes instead."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-2", 1.0)
    seed_shed(commander, "W:w-2", {"alice": 5.0, "bob": 3.0, "carol": 2.0})
    commander.moving["alice"] = asyncio.Event()
    assert commander.pick_rebalance_users("W:w-2", 0.6, target_empty=True) == ["bob", "carol"]
    # And the drain's own selection leaves it out for the same reason.
    assert commander.drain_order("W:w-2") == ["bob", "carol"]


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


async def test_a_replacement_that_never_registers_leaves_no_state_behind() -> None:
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
        # The failure poisons nothing: the pool still has a worker that can
        # receive, so the next entry — new or resident — is served as before.
        assert commander.worker_for("guest-2") == commander.reception
        assert commander.worker_for("alice") == source
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
# The condemnations: what the plan replaces, and whether it spawns
# ----------------------------------------------------------------------

MB = 1024 * 1024


def leaking_commander(tmp_path: Any, **kwargs: Any) -> UserStickyCommander:
    """A commander with a memory limit — without one nothing ever recycles."""
    return UserStickyCommander(
        workers=0, path=str(tmp_path / "hub.sock"), memory_limit_mb=1024, **kwargs
    )


def floor_at(commander: UserStickyCommander, name: str, fraction: float) -> None:
    """Seed the worker's floor series so its last floor is ``fraction`` of the limit."""
    series = commander.worker_roster[name]["floors"]
    series.clear()
    series.append({"ts": 0.0, "floor": (commander.memory_limit_mb or 0) * MB * fraction})


def wasteful(commander: UserStickyCommander, name: str, ratio: float) -> None:
    """Seed the worker's window so its last report holds ``ratio`` of its floor unused."""
    floor = 100 * MB
    reusable = ratio * floor
    commander.worker_roster[name]["occupancy"].clear()
    commander.record_occupancy(
        name,
        {
            "cpu": 0.0,
            "rss": floor + reusable,
            "reusable": reusable,
            "executor": {"busy": 0, "total": 0},
        },
    )


def test_the_plan_condemns_necessity_before_convenience(tmp_path: Any) -> None:
    """R5's own order inside a plan: the floors that reached their budget first,
    then the wasteful ones from the worst down."""
    commander = leaking_commander(tmp_path)
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(commander, name)
    floor_at(commander, "W:w-4", 0.9)  # necessity: the floor has spent its budget
    wasteful(commander, "W:w-2", 1.0)
    wasteful(commander, "W:w-3", 3.0)  # the most wasteful of the two
    assert commander.condemned_workers() == ["W:w-4", "W:w-3", "W:w-2"]


def test_a_worker_condemned_on_both_counts_is_named_once(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    floor_at(commander, "W:w-2", 0.9)
    wasteful(commander, "W:w-2", 3.0)
    assert commander.condemned_workers() == ["W:w-2"]


def test_a_healthy_pool_condemns_nobody(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    floor_at(commander, "W:w-2", 0.1)
    wasteful(commander, "W:w-2", 0.1)
    assert commander.condemned_workers() == []


def test_the_rebalance_comes_before_the_condemnations(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.9)  # hot AND sick: the latency comes first
    floor_at(commander, "W:w-1", 0.9)
    plan = commander.build_plan()
    assert plan[0] == {"op": "rebalance"}
    assert plan[1]["op"] == "replace"
    assert plan[1]["worker"] == "W:w-1"


def test_the_condemnations_come_before_the_compaction(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path, compaction_margin=0.4, spawn_margin=0.2)
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    floor_at(commander, "W:w-2", 0.9)
    plan = commander.build_plan()
    assert [step["op"] for step in plan] == ["replace", "compact"]
    # And the condemned worker is not ALSO folded: its replacement step already
    # takes it out, so a fold aimed at it would find nothing left to retire.
    assert plan[1]["worker"] == "W:w-3"


def test_a_condemnation_the_pool_absorbs_asks_for_no_new_process(tmp_path: Any) -> None:
    """R4's gate, read at build time: the room is already there, so the worker is
    condemned and evacuated without a replacement."""
    commander = leaking_commander(tmp_path, compaction_margin=0.4, spawn_margin=0.2)
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    commander.assign_user("alice", "W:w-2")
    floor_at(commander, "W:w-2", 0.9)
    assert commander.pool_absorbs("W:w-2") is True
    replace = [step for step in commander.build_plan() if step["op"] == "replace"]
    assert replace == [{"op": "replace", "worker": "W:w-2", "spawn": False}]


def test_a_condemnation_the_pool_cannot_absorb_spawns(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.5)  # the reception is full to its own threshold
    floor_at(commander, "W:w-2", 0.9)
    assert commander.pool_absorbs("W:w-2") is False
    replace = [step for step in commander.build_plan() if step["op"] == "replace"]
    assert replace == [{"op": "replace", "worker": "W:w-2", "spawn": True}]


def test_condemning_the_reception_always_spawns(tmp_path: Any) -> None:
    """R3's statute: the reception's replacement is role continuity, never
    capacity — the weight gate is not even consulted."""
    commander = leaking_commander(tmp_path, compaction_margin=0.4, spawn_margin=0.2)
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    assert commander.reception == "W:w-1"
    assert commander.pool_absorbs("W:w-1") is True  # the room is there, and irrelevant
    floor_at(commander, "W:w-1", 0.9)
    replace = [step for step in commander.build_plan() if step["op"] == "replace"]
    assert replace == [{"op": "replace", "worker": "W:w-1", "spawn": True}]


def test_the_compaction_takes_the_empty_workers_first(tmp_path: Any) -> None:
    """Emptiest first is literal: a worker with nobody aboard costs no move at
    all, so it is folded before the loaded ones the drain has to empty."""
    roomy = UserStickyCommander(
        workers=0, path=str(tmp_path / "hub.sock"), compaction_margin=0.4, spawn_margin=0.2
    )
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(roomy, name)
    roomy.assign_user("alice", "W:w-2")
    load(roomy, "W:w-2", 0.1)
    load(roomy, "W:w-3", 0.4)
    load(roomy, "W:w-4", 0.2)
    assert roomy.compaction_order() == ["W:w-3", "W:w-4", "W:w-2"]


def test_the_compaction_stops_at_the_capacity_rule_of_the_planned_pool(tmp_path: Any) -> None:
    """Each fold is judged on the pool as this plan would leave it, not on the
    one it started from: three idle workers hold 2.5, so the first fold leaves
    1.5, the second 0.5 — under the 0.6 margin, and never planned."""
    tight = UserStickyCommander(
        workers=0, path=str(tmp_path / "hub.sock"), compaction_margin=0.6
    )
    for name in ("W:w-1", "W:w-2", "W:w-3"):
        enroll(tight, name)
    assert len(tight.compaction_order()) == 1


# ----------------------------------------------------------------------
# The condemnation stamp: a plan never sheds onto what it takes out
# ----------------------------------------------------------------------


def shedding_world(occupancy_world: Any, **kwargs: Any) -> UserStickyCommander:
    """The panel's repro pool: a hot reception over three empty workers.

    The world seeds the readings; the two residents also get the recent service
    time a shed is weighed on, which no occupancy picture carries.
    """
    commander = occupancy_world("shedding_pool", **kwargs)
    for user in ("alice", "bob"):
        commander.count_user_consumption(user, 1.0)
    return commander


@pytest.mark.parametrize(
    ("compaction_margin", "spawn_margin"),
    [(0.3, 0.2), (COMPACTION_MARGIN, SPAWN_MARGIN)],
    ids=["panel margins", "stock margins"],
)
def test_a_plan_never_sheds_onto_a_worker_a_later_step_takes_out(
    occupancy_world: Any, compaction_margin: float, spawn_margin: float
) -> None:
    """The confirmed critical: the rebalance used to pick the emptiest worker,
    which is exactly the one the compaction that follows folds away — the users
    landed there only to be drained straight back. Naming a worker in a step now
    stamps it ``retiring`` in the same breath, and a retiring worker is nobody's
    destination."""
    commander = shedding_world(
        occupancy_world, compaction_margin=compaction_margin, spawn_margin=spawn_margin
    )
    plan = commander.build_plan()
    assert plan[0] == {"op": "rebalance"}
    leaving = {step["worker"] for step in plan if step["op"] in ("compact", "replace")}
    assert leaving
    assert all(commander.worker_roster[name]["status"] == "retiring" for name in leaving)
    excess = commander.rebalance_excess()
    target = commander.pick_rebalance_target(sum(value for _, value in excess))
    assert target is not None
    assert target not in leaving


async def test_a_mixed_plan_sheds_and_folds_in_one_run(occupancy_world: Any) -> None:
    """Rebalance and compaction in the same plan, executed end to end: the shed
    lands on the ONE worker no fold names, and both folds still run."""
    commander = shedding_world(occupancy_world, compaction_margin=0.3, spawn_margin=0.2)
    commander.target = 4
    moves: list[tuple[str, str]] = []

    async def record(user: str, target: str) -> bool:
        moves.append((user, target))
        commander.assign_user(user, target)
        return True

    commander.move_user = record  # type: ignore[method-assign]
    plan = commander.build_plan()
    assert [step["op"] for step in plan] == ["rebalance", "compact", "compact"]
    folded = [step["worker"] for step in plan if step["op"] == "compact"]
    assert folded == ["W:w-2", "W:w-3"]
    await commander.execute_plan(plan)
    assert moves
    assert {target for _, target in moves} == {"W:w-4"}
    assert all(commander.worker_roster[name]["status"] == "draining" for name in folded)
    assert commander.target == 2
    assert commander.active_plan is None


def test_releasing_a_plan_hands_back_what_it_never_took_out(occupancy_world: Any) -> None:
    """A plan built and then dropped must not leave the pool short of workers:
    the rows it stamped and never moved on go back to being ordinary members."""
    commander = shedding_world(occupancy_world, compaction_margin=0.3, spawn_margin=0.2)
    stamped = [step["worker"] for step in commander.build_plan() if step["op"] == "compact"]
    assert stamped == ["W:w-2", "W:w-3"]
    commander.release_plan()
    assert commander.active_plan is None
    assert all(commander.worker_roster[name]["status"] == "active" for name in stamped)
    assert commander.pick_rebalance_target(0.4) == "W:w-2"


def test_a_retiring_worker_still_serves_who_it_holds(commander: UserStickyCommander) -> None:
    """It is out of every picker, not out of the pool: its residents keep being
    served where their state actually is, and it still counts toward the target
    so the reconcile does not spawn a second worker beside it."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.assign_user("alice", "W:w-2")
    commander.worker_roster["W:w-2"]["status"] = "retiring"
    assert commander.worker_for("alice") == "W:w-2"
    assert commander.living_workers == ["W:w-1", "W:w-2"]
    assert commander.active_workers == ["W:w-1", "W:w-2"]


def test_a_retiring_worker_is_never_where_a_login_is_placed(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    load(commander, "W:w-1", 0.9)  # the reception passes the login on
    commander.worker_roster["W:w-2"]["status"] = "retiring"
    assert commander.pick_placement(commander.active_workers) == "W:w-3"


def test_a_retiring_worker_is_not_room_the_capacity_check_counts_on(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.target = 2
    load(commander, "W:w-1", 0.9)
    commander.worker_roster["W:w-2"]["status"] = "retiring"
    commander.check_capacity()
    assert commander.target == 3


def test_a_retiring_worker_never_takes_a_condemned_worker_s_users(
    commander: UserStickyCommander,
) -> None:
    """The receiver half of the condemnation gate: room sitting on a worker this
    same plan is taking out is not room the next condemnation may count on."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    commander.assign_user("alice", "W:w-2")
    load(commander, "W:w-3", 0.5)  # the fullest that still admits: R4's own answer
    assert commander.pick_best_fit(0.0, exclude="W:w-2") == "W:w-3"
    commander.worker_roster["W:w-3"]["status"] = "retiring"
    assert commander.pick_best_fit(0.0, exclude="W:w-2") == "W:w-1"


def test_a_salvage_never_lands_on_a_retiring_worker(commander: UserStickyCommander) -> None:
    """The rescue path of a move that lost its room picked the emptiest worker of
    all — which during a plan is exactly the one about to be folded away, so the
    salvaged user would be drained straight back."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    load(commander, "W:w-3", 0.4)
    assert commander.salvage_target({"W:w-1"}) == "W:w-2"  # the emptiest of the rest
    commander.worker_roster["W:w-2"]["status"] = "retiring"
    assert commander.salvage_target({"W:w-1"}) == "W:w-3"


def test_a_salvage_with_every_worker_out_reports_no_room(commander: UserStickyCommander) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.worker_roster["W:w-2"]["status"] = "retiring"
    assert commander.salvage_target({"W:w-1"}) is None


def test_the_fold_fallback_never_returns_a_retiring_worker(
    commander: UserStickyCommander,
) -> None:
    """With every gate closed the drain hands the user to the least loaded worker
    anyway — but a worker the same plan is taking out is not a landing either."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    enroll(commander, "W:w-4")
    load(commander, "W:w-1", 1.3)  # the reception, and the fullest of all
    load(commander, "W:w-3", 1.1)
    load(commander, "W:w-4", 1.2)
    assert commander.pick_best_fit(0.0, exclude="W:w-2") is None  # nobody admits
    assert commander.pick_compaction_target("W:w-2") == "W:w-3"
    commander.worker_roster["W:w-3"]["status"] = "retiring"
    assert commander.pick_compaction_target("W:w-2") == "W:w-4"


def test_the_gate_of_a_condemnation_nets_out_what_the_plan_already_takes(tmp_path: Any) -> None:
    """The aggregate half of the gate, read on the pool as this plan would leave
    it: a worker already condemned without a successor is room going away."""
    commander = leaking_commander(tmp_path, compaction_margin=2.0, spawn_margin=0.2)
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(commander, name)
    commander.assign_user("alice", "W:w-3")
    assert commander.pool_absorbs("W:w-3") is True
    assert commander.pool_absorbs("W:w-3", leaving=["W:w-2"]) is False


def test_the_second_condemnation_of_a_tick_is_refused_the_first_s_room(tmp_path: Any) -> None:
    """Two convenience candidates in one plan: the first is absorbed, and the
    second is judged against a pool the first has already left — so it spawns
    instead of counting a gate that is on its way out."""
    commander = leaking_commander(tmp_path, compaction_margin=2.0, spawn_margin=0.2)
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(commander, name)
    wasteful(commander, "W:w-2", 1.0)
    wasteful(commander, "W:w-3", 3.0)  # the worst, condemned first
    assert commander.condemned_workers() == ["W:w-3", "W:w-2"]
    replace = [step for step in commander.build_plan() if step["op"] == "replace"]
    assert replace == [
        {"op": "replace", "worker": "W:w-3", "spawn": False},
        {"op": "replace", "worker": "W:w-2", "spawn": True},
    ]


def test_two_condemnations_a_wide_pool_really_absorbs_both_spawn_nothing(tmp_path: Any) -> None:
    """The other half of the netting: room enough for both gates leaves both
    condemnations replacement-free."""
    commander = leaking_commander(tmp_path, compaction_margin=0.3, spawn_margin=0.2)
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(commander, name)
    wasteful(commander, "W:w-2", 1.0)
    wasteful(commander, "W:w-3", 3.0)
    replace = [step for step in commander.build_plan() if step["op"] == "replace"]
    assert replace == [
        {"op": "replace", "worker": "W:w-3", "spawn": False},
        {"op": "replace", "worker": "W:w-2", "spawn": False},
    ]


async def test_a_pool_with_nothing_wrong_plans_nothing(tmp_path: Any) -> None:
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    assert commander.build_plan() == []
    assert commander.active_plan is None


async def test_the_in_process_worker_is_never_condemned(tmp_path: Any) -> None:
    """The single role's worker IS the commander's process: no successor sheds
    its leak, no retire has a process to end — the plan skips it and a direct
    recycle refuses it."""
    commander = leaking_commander(tmp_path)
    local = enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    commander.worker = SimpleNamespace(name=local)  # type: ignore[assignment]
    floor_at(commander, "W:w-1", 0.9)  # the sickest of the pool, and still skipped
    floor_at(commander, "W:w-2", 0.9)
    assert commander.condemned_workers() == ["W:w-2"]
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


async def test_a_worker_already_evacuating_is_never_condemned_twice(tmp_path: Any) -> None:
    """Several successions may be open at once (R2: possibly several, sequential),
    but never two on the same worker: the flag takes it out of every reading the
    plan is built on."""
    commander = leaking_commander(tmp_path)
    enroll(commander, "W:w-1")
    enroll(commander, "W:evac")
    floor_at(commander, "W:evac", 0.9)
    assert commander.condemned_workers() == ["W:evac"]
    commander.worker_roster["W:evac"]["status"] = "evacuating"
    assert commander.condemned_workers() == []


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
    commander.advance_evacuations()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # Mid-call: nothing moved, and the pool's other forces stayed free.
    assert moved == []
    assert commander.worker_roster["W:w-1"]["status"] == "evacuating"
    # His call closes: the move launches THERE, on the spot.
    commander.close_request("W:w-1", "alice", request)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert moved == ["alice"]
    # The next tick closes the books on the emptied worker.
    commander.advance_evacuations()
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


async def test_a_vanished_user_is_nobody_s_move(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    assert await commander.move_user("ghost", "W:w-1") is False


def test_a_restricted_pool_with_no_receiver_answers_503(tmp_path: Any) -> None:
    """The refusal is gated by the POOL's state, not by the request: a pool that
    could not regenerate turns the stranger away with the honest signal the
    infrastructure already watches, and the door opens the instant a worker can
    receive again."""
    commander = leaking_commander(tmp_path)
    commander.pool_status = "restricted"
    with pytest.raises(HTTPException) as refused:
        commander.worker_for("guest")
    assert refused.value.status == 503
    enroll(commander, "W:w-1")
    commander.pool_status = "ready"
    assert commander.worker_for("guest") == "W:w-1"


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


def test_the_stall_report_repeats_on_the_sysop_cadence(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """One report per ``EVACUATION_WARN_INTERVAL``, not one per tick: the
    condition does not change between beats and the reader is a human."""
    enroll(commander, "W:w-1", status="evacuating")
    commander.assign_user("alice", "W:w-1")
    commander.open_request("W:w-1", "alice", "/op/page_ping")
    row = commander.worker_roster["W:w-1"]
    row["evacuating_since"] = time.monotonic() - CONNECTION_MAX_AGE - 10

    def stall_reports() -> int:
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            commander.warn_stalled_evacuation("W:w-1")
        return sum("stalled" in record.getMessage() for record in caplog.records)

    assert stall_reports() == 1
    assert stall_reports() == 0  # inside the interval: silent
    row["evacuation_warned_at"] = time.monotonic() - EVACUATION_WARN_INTERVAL - 1
    assert stall_reports() == 1  # the interval has passed: reported again


def test_a_rebalance_sheds_onto_the_fullest_worker_that_still_takes_it(
    commander: UserStickyCommander,
) -> None:
    """Consolidate, do not spread: the excess goes to the worker already
    carrying its share, so the emptier rows stay foldable."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    load(commander, "W:w-2", 0.6)
    load(commander, "W:w-3", 0.2)
    # Both are eligible for a 0.2 excess (the ceiling is 0.9): the fuller wins.
    assert commander.pick_rebalance_target(0.2) == "W:w-2"


def test_no_receiver_is_filled_past_its_own_threshold(
    commander: UserStickyCommander,
) -> None:
    """The reception is judged at ``reception_threshold``, so a placement may
    not push it past that gate just because it is the fullest fit."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    reception = commander.reception
    assert reception == "W:w-1"
    load(commander, reception, 0.4)
    load(commander, "W:w-2", 0.1)
    ceiling = commander.worker_threshold(reception)
    assert 0.4 + 0.2 > ceiling  # the reception is the fullest, and out of reach
    assert commander.pick_best_fit(0.2) == "W:w-2"
    assert commander.pick_best_fit(0.05) == reception  # under its own gate: it fits


async def test_the_compaction_narrows_the_target_it_folds(
    commander: UserStickyCommander,
) -> None:
    """One decrement per fold: folding a worker away WITHOUT lowering the
    target would leave the reconcile respawning it forever."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3")
    enroll(commander, "W:w-4")
    commander.target = 4
    await fold(commander)
    # One fold happened (the margin stops the second): target followed it.
    assert commander.target == 3
    assert len(commander.living_workers) == 3


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
        await settled_at(running, "alice", target)
        dropped = await running.forward_call("alice", "/op/drop_user")
        assert dropped["tag"] == "carried"
    finally:
        await running.stop()


# ----------------------------------------------------------------------
# The weight gate: can the rest of the pool take them, and who takes each
# ----------------------------------------------------------------------


def test_the_best_fit_is_the_fullest_worker_that_still_takes_the_weight(
    commander: UserStickyCommander,
) -> None:
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(commander, name)
    load(commander, "W:w-2", 0.6)  # 0.9 with the weight: fits, and fullest of those that do
    load(commander, "W:w-3", 0.8)  # 1.1 with the weight: past the admission ceiling
    load(commander, "W:w-4", 0.1)
    assert commander.pick_best_fit(0.3) == "W:w-2"


def test_the_best_fit_skips_the_condemned_and_whoever_is_not_active(
    commander: UserStickyCommander,
) -> None:
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    enroll(commander, "W:w-3", status="draining")
    load(commander, "W:w-1", 0.9)
    load(commander, "W:w-2", 0.4)
    assert commander.pick_best_fit(0.3) == "W:w-2"
    # Without w-2 there is nobody left: w-1 is over the ceiling, w-3 is not active.
    assert commander.pick_best_fit(0.3, exclude="W:w-2") is None


def test_the_pool_absorbs_a_condemned_worker_with_room_to_spare(
    commander: UserStickyCommander,
) -> None:
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(commander, name)
    load(commander, "W:w-2", 0.4)
    seed_shed(commander, "W:w-2", {"alice": 1.0, "bob": 1.0})
    assert commander.capacity_headroom(exclude="W:w-2") == pytest.approx(2.5)
    assert commander.pool_absorbs("W:w-2") is True


def test_the_absorption_keeps_the_whole_compaction_margin(
    commander: UserStickyCommander,
) -> None:
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(commander, name)
    load(commander, "W:w-2", 0.3)
    seed_shed(commander, "W:w-2", {"alice": 1.0})
    assert commander.capacity_headroom(exclude="W:w-2") == pytest.approx(2.5)
    assert commander.pool_absorbs("W:w-2") is True
    load(commander, "W:w-4", 1.0)  # 1.5 left without w-2: exactly the margin
    assert commander.capacity_headroom(exclude="W:w-2") == pytest.approx(1.5)
    # A margin means a margin: landing ON it is not keeping it. alice still has
    # a home, so the ledger is what refuses here.
    assert commander.pick_best_fit(0.3, exclude="W:w-2") is not None
    assert commander.pool_absorbs("W:w-2") is False


def test_one_unplaceable_user_refuses_the_absorption(commander: UserStickyCommander) -> None:
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4", "W:w-5", "W:w-6"):
        enroll(commander, name)
    for name in ("W:w-1", "W:w-3", "W:w-4", "W:w-5", "W:w-6"):
        load(commander, name, 0.3)
    load(commander, "W:w-2", 1.0)
    seed_shed(commander, "W:w-2", {"alice": 3.0, "bob": 1.0})
    # Room to spare in the aggregate, and bob is placeable — but alice's three
    # quarters of a whole worker fit nowhere: 0.3 + 0.75 is past the ceiling.
    assert commander.capacity_headroom(exclude="W:w-2") == pytest.approx(3.0)
    assert commander.rebalance_weights("W:w-2") == {
        "alice": pytest.approx(0.75),
        "bob": pytest.approx(0.25),
    }
    assert commander.pick_best_fit(0.25, exclude="W:w-2") is not None
    assert commander.pool_absorbs("W:w-2") is False


# ----------------------------------------------------------------------
# The ladder: the five rungs in order, the spawn of spare, the reaper
# ----------------------------------------------------------------------


def frozen_node(freezer: Path) -> Any:
    """``freezer`` as a storage node: a ``site:`` mount over its parent directory.

    The commander speaks storage nodes only; the tests keep the raw ``Path``
    for arranging and asserting what is really on the disk.
    """
    return site_storage(freezer.parent).node(f"site:{freezer.name}")


def ladder_world(occupancy_world: Any, freezer: Path, **kwargs: Any) -> UserStickyCommander:
    """The pool that calls for EVERY rung at once, with the freezer armed.

    A hot reception holding a long-idle user, a worker whose floor has spent its
    budget, an empty worker to fold and a loaded one to keep. The margins are
    chosen so the ledger authorizes exactly one fold, and so that the pool the
    plan would LEAVE — not the one it reads — falls under the spawn margin.
    """
    kwargs.setdefault("compaction_margin", 0.6)
    kwargs.setdefault("spawn_margin", 0.3)
    return occupancy_world(
        "ladder_pool",
        freeze_idle_after=FREEZE_IDLE_AFTER,
        frozen_users_dir=frozen_node(freezer),
        **kwargs,
    )


def age_parcel(freezer: Path, name: str, age: float) -> Path:
    """Write one parcel into the freezer and back-date its mtime by ``age`` seconds."""
    freezer.mkdir(parents=True, exist_ok=True)
    path = freezer / name
    path.write_text("parcel")
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


def test_the_plan_climbs_the_ladder_rung_by_rung(occupancy_world: Any, tmp_path: Any) -> None:
    """The ratified order on a world that triggers all five rungs: the idle user
    goes to disk first, then the excess is shed, then the worker whose floor has
    spent its budget is replaced, then the pool is widened for the shape the plan
    LEAVES — and the fold, which only costs memory, comes last."""
    commander = ladder_world(occupancy_world, tmp_path / "frozen")
    plan = commander.build_plan()
    assert [step["op"] for step in plan] == ["freeze", "rebalance", "replace", "spawn", "compact"]
    assert plan[0] == {"op": "freeze", "user": "alice", "worker": "W:w-1"}
    assert plan[2] == {"op": "replace", "worker": "W:w-2", "spawn": False}
    assert plan[4] == {"op": "compact", "worker": "W:w-3"}
    # A freeze step names a USER, so it stamps nothing: the reception stays a
    # full member of the pool, while the two workers the plan takes out are
    # retiring from the build itself.
    assert commander.worker_roster["W:w-1"]["status"] == "active"
    assert commander.worker_roster["W:w-2"]["status"] == "retiring"
    assert commander.worker_roster["W:w-3"]["status"] == "retiring"


def test_the_freeze_rung_sends_the_longest_idle_first(
    occupancy_world: Any, tmp_path: Any
) -> None:
    """The rung is the valve's own order: whoever has been idle longest goes
    first, whatever worker holds it."""
    commander = occupancy_world(
        "loaded_pool",
        freeze_idle_after=FREEZE_IDLE_AFTER,
        frozen_users_dir=frozen_node(tmp_path / "frozen"),
    )
    # bob's worker sits at 0.95 of its budget, so its valve is down to the floor:
    # past it at five thousand seconds, and longer idle than alice's 3600.
    commander.worker_roster["W:w-2"]["users"]["bob"]["last_activity_ts"] = time.time() - 5000.0
    plan = commander.build_plan()
    assert [(step["user"], step["worker"]) for step in plan if step["op"] == "freeze"] == [
        ("bob", "W:w-2"),
        ("alice", "W:w-1"),
    ]


@pytest.mark.parametrize(
    ("spawn_margin", "spawns"),
    [(0.3, True), (0.1, False)],
    ids=["short of the margin", "comfortable"],
)
def test_the_spawn_rung_reads_the_pool_the_plan_would_leave(
    occupancy_world: Any, tmp_path: Any, spawn_margin: float, spawns: bool
) -> None:
    """R5's create half: the pool as it reads NOW has room to spare, and would
    still be asked for nothing. It is what this plan takes out of it — one
    condemnation the weight gate absorbs, plus one fold — that leaves it short."""
    commander = ladder_world(occupancy_world, tmp_path / "frozen", spawn_margin=spawn_margin)
    assert commander.capacity_headroom() == pytest.approx(1.95)
    assert commander.needs_spare_capacity() is False
    assert commander.needs_spare_capacity(["W:w-2", "W:w-3"]) is spawns
    plan = commander.build_plan()
    assert bool([step for step in plan if step["op"] == "spawn"]) is spawns


def test_a_worker_replaced_one_for_one_leaves_the_ledger_alone(
    occupancy_world: Any, tmp_path: Any
) -> None:
    """Only the workers going out WITHOUT a successor are read as leaving: a
    replacement covers its source one for one, and its users land on it."""
    commander = ladder_world(occupancy_world, tmp_path / "frozen")
    assert commander.needs_spare_capacity(["W:w-2", "W:w-3"]) is True
    assert commander.needs_spare_capacity(["W:w-3"]) is False


def test_the_plan_never_spawns_past_max_workers(
    occupancy_world: Any, tmp_path: Any, caplog: Any
) -> None:
    """The configured ceiling is a hard one wherever a spawn is decided: the rung
    is not climbed, and the refusal is a log line for the sysop."""
    commander = ladder_world(occupancy_world, tmp_path / "frozen", max_workers=4)
    commander.target = 4
    with caplog.at_level(logging.WARNING):
        plan = commander.build_plan()
    assert not [step for step in plan if step["op"] == "spawn"]
    assert "max_workers=4" in caplog.text
    # The rungs around it are unaffected: the plan is the same minus the spawn.
    assert [step["op"] for step in plan] == ["freeze", "rebalance", "replace", "compact"]


async def test_the_executor_runs_the_freeze_and_the_spawn_steps(
    commander: UserStickyCommander,
) -> None:
    """The two new rungs, executed: the freezer is asked for the user the step
    names, and the spawn raises the target BEFORE it waits for its child, so the
    reconcile never reads the fresh process as a surplus."""
    enroll(commander, "W:w-1")
    commander.target = 1
    frozen: list[str] = []

    async def record_freeze(user: str) -> bool:
        frozen.append(user)
        return True

    def record_spawn() -> str:
        assert commander.target == 2
        return enroll(commander, "W:w-2")

    commander.freeze_user = record_freeze  # type: ignore[method-assign]
    commander.spawn_worker = record_spawn  # type: ignore[method-assign]
    await commander.execute_plan(
        [{"op": "freeze", "user": "alice", "worker": "W:w-1"}, {"op": "spawn"}]
    )
    assert frozen == ["alice"]
    assert commander.target == 2
    assert commander.worker_roster["W:w-2"]["status"] == "active"
    assert commander.active_plan is None


def test_the_reaper_takes_the_expired_parcels_and_only_those(tmp_path: Any) -> None:
    """Housekeeping on the freezer's disk, and nothing else: a parcel past its own
    class lifetime goes, one still inside it is left exactly where it is. The
    guest's day and the user's week are read off the file name."""
    freezer = tmp_path / "frozen"
    commander = UserStickyCommander(
        workers=0,
        path=str(tmp_path / "hub.sock"),
        freeze_idle_after=FREEZE_IDLE_AFTER,
        frozen_users_dir=frozen_node(freezer),
    )
    age_parcel(freezer, "alice", 60.0)
    age_parcel(freezer, "bob", FROZEN_USER_LIFETIME + 60.0)
    age_parcel(freezer, f"{GUEST_PREFIX}s1", FROZEN_GUEST_LIFETIME - 60.0)
    age_parcel(freezer, f"{GUEST_PREFIX}s2", FROZEN_GUEST_LIFETIME + 60.0)
    # A guest a day and a half old is expired; a USER of the very same age is not.
    age_parcel(freezer, "dave", FROZEN_GUEST_LIFETIME + 60.0)
    commander.reap_frozen_files()
    assert sorted(path.name for path in freezer.iterdir()) == [
        "alice",
        "dave",
        f"{GUEST_PREFIX}s1",
    ]


def test_the_reaper_has_nothing_to_sweep_before_the_first_parcel(tmp_path: Any) -> None:
    """Both silent cases: the freezer disarmed altogether, and armed on a
    directory no freeze has created yet."""
    disarmed = UserStickyCommander(workers=0, path=str(tmp_path / "hub.sock"))
    assert disarmed.frozen_users_dir is None
    disarmed.reap_frozen_files()
    freezer = tmp_path / "frozen"
    armed = UserStickyCommander(
        workers=0,
        path=str(tmp_path / "hub2.sock"),
        freeze_idle_after=FREEZE_IDLE_AFTER,
        frozen_users_dir=frozen_node(freezer),
    )
    armed.reap_frozen_files()
    assert not freezer.exists()


# ----------------------------------------------------------------------
# Failure semantics: the plan aborts, the pool restricts, the hard restart
# ----------------------------------------------------------------------


async def test_a_replace_the_pool_cannot_regenerate_aborts_the_plan(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """A step that REPORTS its failure ends the plan exactly like one that
    raises: what failed is the pool's ability to put a process up, so every step
    below it was decided against a world that no longer holds. The escalation
    goes first — and with no freezer there is no hard restart to escalate to,
    since killing a worker would throw its users' slices away."""
    for name in ("W:w-1", "W:w-2", "W:w-3"):
        enroll(commander, name)
    commander.target = 3
    drained: list[str] = []

    async def never_succeeds(name: str, spawn: bool = True) -> bool:
        return False

    async def record_drain(name: str) -> bool:
        drained.append(name)
        return True

    commander.recycle_worker = never_succeeds  # type: ignore[method-assign]
    commander.drain_worker = record_drain  # type: ignore[method-assign]
    plan = [
        {"op": "replace", "worker": "W:w-2", "spawn": True},
        {"op": "compact", "worker": "W:w-3"},
    ]
    commander.active_plan = plan
    commander.worker_roster["W:w-3"]["status"] = "retiring"
    with caplog.at_level(logging.ERROR):
        await commander.execute_plan(plan)
    assert "plan aborted: replace step failed on W:w-2" in caplog.text
    assert drained == []
    assert commander.pool_status == "restricted"
    assert commander.active_plan is None
    # The fold that never ran gets its worker back, like any released plan.
    assert commander.worker_roster["W:w-3"]["status"] == "active"


async def test_a_spawn_whose_child_never_registers_aborts_the_plan(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """The widening half: the child is given its 30 seconds and never presents
    itself, so the manoeuvre closes its own stillborn, gives the target back and
    ends the plan — the next tick reads the world and decides again."""
    enroll(commander, "W:w-1")
    commander.target = 1
    commander.READY_TIMEOUT = 0.05
    rebalanced: list[float] = []
    born: list[str] = []

    def stillborn() -> str:
        name = commander.next_worker_name()
        commander.worker_roster[name] = commander.new_roster_row(0, None)
        born.append(name)
        return name

    async def record_rebalance(now: float | None = None) -> None:
        rebalanced.append(0.0)

    commander.spawn_worker = stillborn  # type: ignore[method-assign]
    commander.rebalance_pass = record_rebalance  # type: ignore[method-assign]
    with caplog.at_level(logging.ERROR):
        await commander.execute_plan([{"op": "spawn"}, {"op": "rebalance"}])
    assert f"plan aborted: spawn step failed on {born[0]}" in caplog.text
    assert rebalanced == []
    assert commander.target == 1
    assert commander.worker_roster[born[0]]["status"] == "dead"
    assert commander.pool_status == "restricted"
    assert commander.active_plan is None


def test_a_restricted_pool_turns_strangers_away_and_serves_its_own(tmp_path: Any) -> None:
    """Who is inside is served exactly as ever — placed or hibernating — and only
    a stranger, whom the pool holds nothing of, is refused. The refusal carries
    the one honest answer to "when should I come back": the interval at which the
    pool decides its own shape."""
    freezer = tmp_path / "frozen"
    freezer.mkdir()
    (freezer / "bob").write_text("parcel")
    commander = UserStickyCommander(
        workers=0,
        path=str(tmp_path / "hub.sock"),
        freeze_idle_after=FREEZE_IDLE_AFTER,
        frozen_users_dir=frozen_node(freezer),
    )
    enroll(commander, "W:w-1")
    commander.assign_user("alice", "W:w-1")
    commander.pool_status = "restricted"
    assert commander.worker_for("alice") == "W:w-1"
    assert commander.worker_for("bob") == "W:w-1"
    with pytest.raises(HTTPException) as refused:
        commander.worker_for("stranger")
    assert refused.value.status == 503
    assert refused.value.headers == [
        (b"retry-after", str(int(commander.decision_interval)).encode())
    ]


async def test_the_first_register_lifts_the_restriction() -> None:
    """The one POSITIVE proof that the pool can regenerate is a child presenting
    itself: whatever refused to start when the plan aborted, the door opens
    again the moment one does."""
    running = LocalPool()
    await running.start(1)
    try:
        running.commander.pool_status = "restricted"
        await running.add_worker()
        assert running.commander.pool_status == "ready"
    finally:
        await running.stop()


async def test_stopping_the_pool_lifts_the_restriction() -> None:
    """The restriction described a pool that could not regenerate; a pool that
    is closing has nothing left to restrict."""
    running = LocalPool()
    await running.start(1)
    running.commander.pool_status = "restricted"
    await running.stop()
    assert running.commander.pool_status == "ready"


def spawn_into(running: LocalPool) -> Any:
    """A ``spawn_worker`` that raises a real in-process worker instead of a child.

    The roster row is written synchronously — the caller gets a name it can wait
    on at once — and the channel attach, which is what makes the REGISTER, rides
    a task the wait's own polling lets through.
    """
    commander = running.commander

    def spawn() -> str:
        name = commander.next_worker_name()
        commander.worker_roster[name] = commander.new_roster_row(os.getpid(), None)
        asyncio.get_running_loop().create_task(running.add_worker(name))
        return name

    return spawn


async def a_user_on_a_second_worker(running: LocalPool) -> str:
    """Seed one live user with a page and move it off the reception.

    The target is stated too — the pool was populated by hand — because a hard
    restart holds the dying worker's seat, and a seat is a number.
    """
    commander = running.commander
    commander.target = len(running.names)
    sick = running.names[1]
    await seed_live_guest(running, str(commander.reception))
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await settled_at(commander, "alice", str(commander.reception))
    assert await commander.move_user("alice", sick)
    return sick


async def test_a_hard_restart_parks_its_users_kills_and_leaves_them_to_wake(
    tmp_path: Any,
) -> None:
    """The escalation, end to end: the soft succession is impossible, so the sick
    process dies FIRST and the fresh one is born in the space its death frees.
    Nothing is lost by dying — every user goes to the freezer before the kill —
    and the refill is LAZY: the restart wakes nobody, and alice comes out of her
    file on her own next request, with her page alive again."""
    freezer = tmp_path / "frozen"
    running = LocalPool(
        worker_class=PageWorker,
        freeze_idle_after=FREEZE_IDLE_AFTER,
        frozen_users_dir=frozen_node(freezer),
    )
    await running.start(2)
    commander = running.commander
    try:
        sick = await a_user_on_a_second_worker(running)
        commander.spawn_worker = spawn_into(running)  # type: ignore[method-assign]
        assert await commander.hard_restart(sick) is True
        assert commander.worker_roster[sick]["status"] == "draining"
        # The seat was held across the kill: one worker out, one worker in.
        assert commander.target == 2
        assert len(running.names) == 3
        # Nobody was woken back: the user is still in her file when it returns.
        assert commander.user_worker_map["alice"] == FROZEN
        assert (freezer / "alice").exists()
        envelope = await commander.forward_envelope("alice", "/op/page_ping", {"page_id": "p1"})
        assert envelope["result"]["page_id"] == "p1"
        destination = commander.user_worker_map["alice"]
        assert destination != sick
        assert not (freezer / "alice").exists()
    finally:
        await running.stop()


async def test_a_hard_restart_skips_a_user_it_cannot_park(tmp_path: Any, caplog: Any) -> None:
    """The park loop awaits each user's hold and re-reads the map, exactly as
    ``resolve_worker`` does — and a user that still refuses to go to disk is
    SKIPPED with a WARNING rather than holding the restart: its slice dies with
    the process and it comes back at its next login. Loud, and accepted."""
    freezer = tmp_path / "frozen"
    running = LocalPool(
        worker_class=PageWorker,
        freeze_idle_after=FREEZE_IDLE_AFTER,
        frozen_users_dir=frozen_node(freezer),
    )
    await running.start(2)
    commander = running.commander
    try:
        sick = await a_user_on_a_second_worker(running)
        commander.spawn_worker = spawn_into(running)  # type: ignore[method-assign]

        async def never_parks(user: str) -> bool:
            return False

        commander.freeze_user = never_parks  # type: ignore[method-assign]
        with caplog.at_level(logging.WARNING):
            assert await commander.hard_restart(sick) is True
        assert "alice did not park" in caplog.text
        assert not (freezer / "alice").exists()
    finally:
        await running.stop()


async def test_a_hard_restart_that_fails_too_leaves_everybody_parked(
    tmp_path: Any, caplog: Any
) -> None:
    """The worst case, and why the parking comes first: not even the fresh child
    registers. Nothing is lost — the users wait in their files, which outlive the
    whole pool — the plan ends, and the pool stops taking strangers in until a
    worker proves it can be born."""
    freezer = tmp_path / "frozen"
    running = LocalPool(
        worker_class=PageWorker,
        freeze_idle_after=FREEZE_IDLE_AFTER,
        frozen_users_dir=frozen_node(freezer),
    )
    await running.start(2)
    commander = running.commander
    try:
        sick = await a_user_on_a_second_worker(running)
        commander.READY_TIMEOUT = 0.05

        def stillborn() -> str:
            name = commander.next_worker_name()
            commander.worker_roster[name] = commander.new_roster_row(0, None)
            return name

        async def never_succeeds(name: str, spawn: bool = True) -> bool:
            return False

        commander.spawn_worker = stillborn  # type: ignore[method-assign]
        commander.recycle_worker = never_succeeds  # type: ignore[method-assign]
        plan = [{"op": "replace", "worker": sick, "spawn": True}]
        commander.active_plan = plan
        with caplog.at_level(logging.ERROR):
            await commander.execute_plan(plan)
        assert f"plan aborted: replace step failed on {sick}" in caplog.text
        assert commander.pool_status == "restricted"
        assert commander.user_worker_map["alice"] == FROZEN
        assert (freezer / "alice").exists()
        # A REGISTER is the proof the pool was waiting for: the door opens and
        # the parked user comes back out of its file on its next request.
        commander.spawn_worker = spawn_into(running)  # type: ignore[method-assign]
        await running.add_worker()
        assert commander.pool_status == "ready"
        envelope = await commander.forward_envelope("alice", "/op/page_ping", {"page_id": "p1"})
        assert envelope["result"]["page_id"] == "p1"
    finally:
        await running.stop()


# ----------------------------------------------------------------------
# What the suite was not saying: the claim's ordinary round trip, the tick's
# own bookkeeping, the execute-time guards, the two tuning knobs, the order
# ----------------------------------------------------------------------


async def test_a_plan_that_finishes_hands_its_claim_back(commander: UserStickyCommander) -> None:
    """The whole lifecycle of the claim, on the path a pool actually takes: a plan
    that RUNS must unclaim too, or the shape of the pool is frozen for the life of
    the process and every later tick answers with nothing."""
    ran: list[str] = []

    async def quiet_rebalance(now: float | None = None) -> None:
        ran.append("rebalance")

    commander.rebalance_pass = quiet_rebalance  # type: ignore[method-assign]
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.9)
    plan = commander.build_plan()
    assert plan == [{"op": "rebalance"}]
    assert commander.active_plan == plan
    await commander.execute_plan(plan)
    assert ran == ["rebalance"]
    assert commander.active_plan is None
    # And the proof that the release is what the next tick needed: the same pool
    # still calls for the same plan, and is free to build it again.
    assert commander.build_plan() == plan


async def test_every_tick_closes_the_open_evacuations_first(
    commander: UserStickyCommander,
) -> None:
    """The bookkeeping of the evacuations has ONE caller in the whole of ``src``:
    this line of the tick. Nothing else would notice if it stopped running."""
    closed: list[str] = []

    def record() -> None:
        closed.append("advance")

    commander.advance_evacuations = record  # type: ignore[method-assign]
    commander.decision_interval = 0.01
    enroll(commander, "W:w-1")
    ticking = asyncio.create_task(commander.planner())
    try:
        await asyncio.sleep(0.05)
    finally:
        ticking.cancel()
    assert closed  # the tick closed the books before deciding anything


def spy_on_drains(commander: UserStickyCommander) -> list[str]:
    """Record every drain the executor asks for, and refuse them all."""
    drained: list[str] = []

    async def refuse(worker: str) -> bool:
        drained.append(worker)
        return False

    commander.drain_worker = refuse  # type: ignore[method-assign]
    return drained


async def test_a_fold_of_a_worker_that_left_the_pool_is_skipped(
    commander: UserStickyCommander,
) -> None:
    """The plan was ordered against a pool the steps before it have since changed:
    a row a replacement took out is not drained on top of that — ``retire`` would
    raise on it and abort every step left."""
    for name in ("W:w-1", "W:w-2", "W:w-3"):
        enroll(commander, name)
    drained = spy_on_drains(commander)
    commander.worker_roster["W:w-2"]["status"] = "evacuating"  # a replace step got there first
    await commander.execute_plan([{"op": "compact", "worker": "W:w-2"}])
    assert drained == []


async def test_a_fold_of_the_worker_that_became_the_reception_is_skipped(
    commander: UserStickyCommander,
) -> None:
    """The reception is never folded away, and a replacement ahead of this step
    can hand the role to exactly the worker the fold names."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    drained = spy_on_drains(commander)
    commander.worker_roster["W:w-1"]["status"] = "evacuating"  # w-2 inherits the role
    assert commander.reception == "W:w-2"
    await commander.execute_plan([{"op": "compact", "worker": "W:w-2"}])
    assert drained == []


async def test_a_fold_the_ledger_no_longer_authorizes_is_skipped(
    commander: UserStickyCommander,
) -> None:
    """The second guard: the room the fold was planned against is gone, so it is
    skipped rather than paid for — a whole ``move_user`` per resident."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    drained = spy_on_drains(commander)
    # Two workers hold 1.5 of capacity: without w-2 the headroom is 0.5, under the
    # stock 1.5 margin. No plan would ask for this fold now.
    assert commander.capacity_headroom(exclude="W:w-2") <= commander.compaction_margin
    await commander.execute_plan([{"op": "compact", "worker": "W:w-2"}])
    assert drained == []


async def test_a_freeze_of_a_user_already_moving_is_skipped(
    commander: UserStickyCommander,
) -> None:
    """The freezer's contract is that a user whose barrier is already up answers
    False and the plan carries on; the executor honours it instead of walking
    into the raise that guards its direct callers."""
    enroll(commander, "W:w-1")
    commander.assign_user("alice", "W:w-1")
    frozen: list[str] = []

    async def record_freeze(user: str) -> bool:
        frozen.append(user)
        return True

    commander.freeze_user = record_freeze  # type: ignore[method-assign]
    commander.moving["alice"] = asyncio.Event()  # a move got there first
    await commander.execute_plan(
        [{"op": "freeze", "user": "alice", "worker": "W:w-1"}, {"op": "rebalance"}]
    )
    assert frozen == []
    assert commander.active_plan is None


async def test_a_spawn_against_a_full_pool_is_skipped(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """The ceiling is re-asked at execute time: the pool may have reached
    ``max_workers`` since the plan was built, and a skip is not a failure — the
    rungs below it still run."""
    enroll(commander, "W:w-1")
    commander.target = 1
    commander.max_workers = 1
    born: list[str] = []
    rebalanced: list[str] = []

    def record_spawn() -> str:
        born.append("child")
        return enroll(commander, "W:w-2")

    async def record_rebalance(now: float | None = None) -> None:
        rebalanced.append("rebalance")

    commander.spawn_worker = record_spawn  # type: ignore[method-assign]
    commander.rebalance_pass = record_rebalance  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING):
        await commander.execute_plan([{"op": "spawn"}, {"op": "rebalance"}])
    assert born == []
    assert "max_workers=1" in caplog.text
    assert commander.target == 1
    assert rebalanced == ["rebalance"]


async def test_a_spawn_with_a_child_already_on_its_way_is_skipped(
    commander: UserStickyCommander,
) -> None:
    """``rebalance_spawn``'s other guard, applied to the plan's own step: a
    worker already being born is waited for, never stacked on."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2", status="nascent")
    commander.target = 2
    born: list[str] = []

    def record_spawn() -> str:
        born.append("child")
        return enroll(commander, "W:w-3")

    commander.spawn_worker = record_spawn  # type: ignore[method-assign]
    await commander.execute_plan([{"op": "spawn"}])
    assert born == []
    assert commander.target == 2


def test_a_restricted_pool_carries_a_probe_spawn_whatever_the_ledger_says(
    commander: UserStickyCommander,
) -> None:
    """The latch is lifted by positive proof, so the planner has to keep asking
    for it: a pool whose triggers have all lapsed would otherwise build nothing
    for ever and stay restricted for the life of the process."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    assert commander.build_plan() == []  # no trigger left anywhere
    commander.pool_status = "restricted"
    plan = commander.build_plan()
    assert plan == [{"op": "spawn", "probe": True}]
    assert commander.active_plan == plan


def test_the_probe_is_the_plan_s_only_spawn(occupancy_world: Any, tmp_path: Any) -> None:
    """A ladder that already climbs its own spawn rung needs no probe beside it:
    that spawn IS the proof the restriction is waiting for, and two children for
    one tick is a pool widened twice."""
    commander = ladder_world(occupancy_world, tmp_path / "frozen")
    commander.pool_status = "restricted"
    plan = commander.build_plan()
    assert [step["op"] for step in plan] == ["freeze", "rebalance", "replace", "spawn", "compact"]


def test_a_replace_that_spawns_is_proof_enough_and_suppresses_the_probe(
    commander: UserStickyCommander, tmp_path: Any
) -> None:
    """A replace carrying ``spawn`` raises a process of its own, so it answers the
    restriction's one question as well as a bare spawn rung does — and the probe
    that would ride behind it is a second child for the same tick."""
    leaking = leaking_commander(tmp_path)
    enroll(leaking, "W:w-1")
    floor_at(leaking, "W:w-1", 0.9)
    leaking.target = 1
    leaking.pool_status = "restricted"
    plan = leaking.build_plan()
    assert [(step["op"], step.get("spawn")) for step in plan] == [("replace", True)]


async def test_a_probe_skips_when_the_restriction_has_meanwhile_lifted(
    commander: UserStickyCommander,
) -> None:
    """The probe exists to lift the latch, so a latch somebody else lifted between
    the build and the step — a REGISTER landing on the very tick — leaves it
    nothing to prove, and the pool is not widened for nothing."""
    enroll(commander, "W:w-1")
    commander.target = 1
    born: list[str] = []
    commander.spawn_worker = lambda: born.append("child") or "W:w-9"  # type: ignore[method-assign]
    commander.pool_status = "ready"
    await commander.execute_plan([{"op": "spawn", "probe": True}])
    assert born == []
    assert commander.target == 1


async def test_the_probe_rides_the_tail_so_a_failed_one_costs_the_ladder_nothing(
    occupancy_world: Any, tmp_path: Any, caplog: Any
) -> None:
    """The probe is a retry, not a prerequisite: nothing below it reads the
    widening, so it goes LAST. A restricted pool therefore still freezes, sheds,
    replaces and folds on the tick whose probe dies — the rungs the ledger asked
    for run before the abort, instead of being suppressed for as long as the
    restriction lasts."""
    commander = ladder_world(occupancy_world, tmp_path / "frozen", spawn_margin=0.0)
    commander.pool_status = "restricted"
    commander.READY_TIMEOUT = 0.05
    ran: list[str] = []
    born: list[str] = []

    async def record_freeze(user: str) -> bool:
        ran.append(f"freeze:{user}")
        return True

    async def record_rebalance(now: float | None = None) -> None:
        ran.append("rebalance")

    async def record_recycle(name: str, spawn: bool = True) -> bool:
        ran.append(f"replace:{name}")
        return True

    async def record_drain(name: str) -> bool:
        ran.append(f"compact:{name}")
        return True

    def stillborn() -> str:
        name = commander.next_worker_name()
        commander.worker_roster[name] = commander.new_roster_row(0, None)
        born.append(name)
        return name

    commander.freeze_user = record_freeze  # type: ignore[method-assign]
    commander.rebalance_pass = record_rebalance  # type: ignore[method-assign]
    commander.recycle_worker = record_recycle  # type: ignore[method-assign]
    commander.drain_worker = record_drain  # type: ignore[method-assign]
    commander.spawn_worker = stillborn  # type: ignore[method-assign]
    plan = commander.build_plan()
    assert [step["op"] for step in plan] == ["freeze", "rebalance", "replace", "compact", "spawn"]
    with caplog.at_level(logging.ERROR):
        await commander.execute_plan(plan)
    assert ran == ["freeze:alice", "rebalance", "replace:W:w-2", "compact:W:w-3"]
    assert f"plan aborted: spawn step failed on {born[0]}" in caplog.text
    assert commander.pool_status == "restricted"
    assert commander.active_plan is None


async def test_a_probe_spawn_that_registers_lifts_the_restriction() -> None:
    """The retry closing the loop: the pool that could not regenerate builds its
    probe, the child presents itself, and the REGISTER opens the door — no
    trigger of the original abort has to still hold."""
    running = LocalPool()
    await running.start(1)
    commander = running.commander
    try:
        commander.pool_status = "restricted"
        commander.spawn_worker = spawn_into(running)  # type: ignore[method-assign]
        widened = commander.target + 1
        plan = commander.build_plan()
        assert plan == [{"op": "spawn", "probe": True}]
        await commander.execute_plan(plan)
        assert commander.pool_status == "ready"
        assert commander.target == widened
    finally:
        await running.stop()


def test_the_floor_limit_ratio_the_commander_was_given_is_the_one_that_condemns(
    tmp_path: Any,
) -> None:
    """The knob is plumbed, not only arithmetically right: a commander configured
    to condemn later must not condemn at the default budget, and one configured to
    condemn earlier must."""
    stock = leaking_commander(tmp_path)  # FLOOR_LIMIT_RATIO, 0.8 of the limit
    enroll(stock, "W:w-1")
    floor_at(stock, "W:w-1", 0.6)
    assert stock.necessity_candidates() == []

    early = leaking_commander(tmp_path, floor_limit_ratio=0.5)
    enroll(early, "W:w-1")
    floor_at(early, "W:w-1", 0.6)
    assert early.necessity_candidates() == ["W:w-1"]

    late = leaking_commander(tmp_path, floor_limit_ratio=0.95)
    enroll(late, "W:w-1")
    floor_at(late, "W:w-1", 0.9)  # the stock budget would condemn this floor
    assert late.necessity_candidates() == []


def test_the_waste_ratio_the_commander_was_given_is_the_one_that_condemns(
    tmp_path: Any,
) -> None:
    """The same for the convenience trigger: an operator raising the tolerance
    stops the churn, one lowering it starts it."""
    stock = leaking_commander(tmp_path)  # WASTE_RATIO, half the floor
    enroll(stock, "W:w-1")
    wasteful(stock, "W:w-1", 0.3)
    assert stock.convenience_candidates() == []

    fussy = leaking_commander(tmp_path, waste_ratio=0.2)
    enroll(fussy, "W:w-1")
    wasteful(fussy, "W:w-1", 0.3)
    assert fussy.convenience_candidates() == ["W:w-1"]

    tolerant = leaking_commander(tmp_path, waste_ratio=1.0)
    enroll(tolerant, "W:w-1")
    wasteful(tolerant, "W:w-1", 0.7)  # the stock tolerance would condemn this waste
    assert tolerant.convenience_candidates() == []


def test_the_loaded_workers_are_folded_by_ascending_load(tmp_path: Any) -> None:
    """The second half of emptiest-first, with three loaded workers so the sort has
    something to say: the lightest goes first, because the compaction is ACTIVE and
    pays a move for every user it finds aboard."""
    roomy = UserStickyCommander(
        workers=0, path=str(tmp_path / "hub.sock"), compaction_margin=0.3, spawn_margin=0.2
    )
    for name in ("W:w-1", "W:w-2", "W:w-3", "W:w-4"):
        enroll(roomy, name)
    for worker, user, saturation in (
        ("W:w-2", "alice", 0.4),
        ("W:w-3", "bob", 0.1),
        ("W:w-4", "carol", 0.25),
    ):
        roomy.assign_user(user, worker)
        load(roomy, worker, saturation)
    assert not roomy.empty_workers()  # nothing is free: the sort decides alone
    assert roomy.compaction_order() == ["W:w-3", "W:w-4", "W:w-2"]


def test_a_candidate_landing_exactly_on_its_ceiling_is_refused(
    commander: UserStickyCommander,
) -> None:
    """The admission ceiling is strict, and the edge is asserted ON it: a worker
    that would land exactly at its own threshold takes nobody."""
    enroll(commander, "W:w-1")
    enroll(commander, "W:w-2")
    load(commander, "W:w-1", 0.9)  # the reception is far past its own lower gate
    load(commander, "W:w-2", 0.75)
    saturation = commander.evaluator.worker_saturation("W:w-2")
    weight = 1.0 - saturation
    assert saturation + weight == 1.0  # the edge is exact, not straddled
    assert commander.pick_best_fit(weight) is None
    assert commander.pick_best_fit(weight - 0.01) == "W:w-2"


def test_the_reception_is_never_filled_past_its_own_ceiling(
    commander: UserStickyCommander,
) -> None:
    """The Phase 3 ceiling at its edge: the gate the reception is judged at, not
    the flat 1.0 — a weight the whole worker would take is refused by the role."""
    enroll(commander, "W:w-1")
    load(commander, "W:w-1", 0.25)
    saturation = commander.evaluator.worker_saturation("W:w-1")
    weight = commander.reception_threshold - saturation
    assert saturation + weight == commander.reception_threshold
    assert weight < 1.0  # a flat ceiling would have admitted it
    assert commander.pick_best_fit(weight) is None
    assert commander.pick_best_fit(weight - 0.01) == "W:w-1"
