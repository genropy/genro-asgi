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

"""Reception, sticky routing, the push login and its placement.

The pool here is real but in-process: two ``UserStickyWorker`` attached to the
commander's own hub over ``LocalChannel`` pairs, so every frame still crosses
encode/decode and the placement happens over ordinary CALLs — only the fork is
missing. One subprocess smoke at the end proves the same sequence survives a
real socket and a real child.

The placement decisions are pure bookkeeping and are asserted without a wire
at all.
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any

import pytest

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


class LocalPool:
    """A commander whose workers live in this process, on LocalChannel pairs.

    The workers are wired exactly like spawned ones — a roster entry, a REGISTER
    over the channel, the same fold — with ``process=None`` where the OS handle
    would be. Phase 7 turns this wiring into the commander's own single role.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.commander = UserStickyCommander(workers=0, **kwargs)
        self.workers: dict[str, UserStickyWorker] = {}

    async def start(self, count: int) -> None:
        await self.commander.start()
        for _ in range(count):
            await self.add_worker()

    async def add_worker(self) -> str:
        name = self.commander.next_worker_name()
        self.commander.worker_roster[name] = self.commander.new_roster_row(os.getpid(), None)
        worker = UserStickyWorker(name)
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
            {"op": "change_connection_user", "seq": 2, "user": "alice", "previous_user": "sess-1"},
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
        {"op": "change_connection_user", "seq": 2, "user": "alice", "previous_user": "sess-1"},
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
    await pool.commander.forward_call("sess-1", "/op/new_user", {"tag": "carried"})
    entry = await pool.commander.forward_call(
        "sess-1", "/op/change_connection_user", {"user": "alice"}
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
    await pool.commander.forward_call("sess-1", "/op/new_user", {"tag": "carried"})
    await pool.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
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
    await commander.forward_call("sess-1", "/op/new_user", {"tag": "carried"})
    login = asyncio.create_task(
        commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
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
    await commander.forward_call("sess-1", "/op/new_user", {"tag": "first"})
    await commander.forward_call("sess-2", "/op/new_user", {"tag": "second"})
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
    await commander.forward_call("sess-1", "/op/new_user")
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
    await commander.forward_call("sess-1", "/op/new_user", {"tag": "carried"})
    login = asyncio.create_task(
        commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
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
        await running.forward_call("sess-1", "/op/new_user", {"tag": "carried"})
        entry = await running.forward_call(
            "sess-1", "/op/change_connection_user", {"user": "alice"}
        )
        assert entry["tag"] == "carried"
        assert running.user_worker_map["alice"] == target
        dropped = await running.forward_call("alice", "/op/drop_user")
        assert dropped["tag"] == "carried"
    finally:
        await running.stop()
