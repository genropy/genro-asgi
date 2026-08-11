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

"""The global store end to end: one master above, one replica per worker.

The pool is real but in-process — two ``UserStickyWorker`` on the commander's own
hub over ``LocalChannel`` pairs — so a write really ascends, the master really
captures it and the change really comes back down a ``/global/changes`` EVENT to
every replica. What the tests pin down is Q-C: a single writer, a grant that
carries the true master state, FIFO waiters, changes that land ONLY at the
release, and a holder's death that releases the lock with the master untouched.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from genro_tytx import from_tytx

from genro_asgi.channel.local import LocalChannel
from genro_asgi.spa.commander import UserStickyCommander
from genro_asgi.spa.global_store import (
    GLOBAL_CHANGES_PATH,
    GLOBAL_SNAPSHOT_PATH,
    CapturingGlobalStore,
    GlobalStore,
)
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


class Stored:
    """A commander with in-process workers and every descending send recorded.

    The workers are wired exactly like spawned ones (a roster row with
    ``process=None``, a REGISTER over the channel, the same fold), so a REGISTER
    really seeds a replica and ``sends`` really shows one EVENT per worker.
    """

    def __init__(self) -> None:
        self.commander = UserStickyCommander(workers=0)
        self.workers: dict[str, UserStickyWorker] = {}
        self.channels: dict[str, LocalChannel] = {}
        self.sends: list[tuple[str, str, Any]] = []

    async def start(self, count: int = 2) -> None:
        await self.commander.start()
        hub_post = self.commander.hub.post

        async def recording_post(name: str, path: str, data: Any = None) -> str:
            self.sends.append((name, path, data))
            return await hub_post(name, path, data)

        self.commander.hub.post = recording_post  # type: ignore[method-assign]
        for _ in range(count):
            await self.add_worker()

    async def add_worker(self) -> str:
        commander = self.commander
        name = commander.next_worker_name()
        commander.worker_roster[name] = commander.new_roster_row(os.getpid(), None)
        worker = UserStickyWorker(name)
        channel = LocalChannel(name)
        worker.attach_channel(channel)
        await channel.connect()
        await commander.hub.attach_local(channel)
        await worker.start()
        self.workers[name] = worker
        self.channels[name] = channel
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

    def replicas(self) -> list[Any]:
        """What every worker's replica currently holds, in pool order."""
        return [worker.global_store for worker in self.workers.values()]

    async def store_set(self, user: str, path: str, value: Any, worker_index: int = 0) -> Any:
        """Write one path through the ordinary op CALL, from a chosen worker."""
        self.commander.assign_user(user, self.names[worker_index])
        return await self.commander.forward_call(
            user, "/op/store_set", {"path": path, "value": value}
        )

    async def store_del(self, user: str, path: str, worker_index: int = 0) -> Any:
        """Remove one path through the ordinary op CALL, from a chosen worker."""
        self.commander.assign_user(user, self.names[worker_index])
        return await self.commander.forward_call(user, "/op/store_del", {"path": path})


@pytest.fixture
async def pool() -> Any:
    running = Stored()
    await running.start()
    try:
        yield running
    finally:
        await running.stop()


# ----------------------------------------------------------------------
# The stores themselves: a replica applies, a capturing one captures
# ----------------------------------------------------------------------


def test_a_replica_applies_a_drained_batch_without_the_forwarding_residue() -> None:
    """The global store has one writer, so there is no second instant to carry."""
    master = CapturingGlobalStore()
    master.set("gnr.a", 1)
    master.bag.set_item("gnr.b", 2, _attributes={"tag": "x"})

    replica = GlobalStore()
    replica.apply_changes(master.drain())

    assert replica.bag["gnr.a"] == 1
    assert replica.bag["gnr.b"] == 2
    assert replica.bag.get_attr("gnr.b") == {"tag": "x"}
    assert "_original_ts" not in replica.bag.get_attr("gnr.b")


def test_a_delete_removes_the_node_rather_than_nulling_it() -> None:
    master = CapturingGlobalStore()
    master.set("gnr.a", 1)
    replica = GlobalStore()
    replica.apply_changes(master.drain())

    master.delete("gnr.a")
    replica.apply_changes(master.drain())

    assert replica.bag["gnr.a"] is None
    assert "a" not in replica.bag["gnr"].keys()


def test_a_snapshot_round_trip_keeps_the_bag_identity() -> None:
    """``worker.global_store`` hands out the Bag itself, so a seed must not swap it."""
    master = CapturingGlobalStore()
    master.set("gnr.a", 1)
    replica = GlobalStore()
    held = replica.bag
    replica.bag.set_item("stale", "gone")

    replica.load_snapshot(master.snapshot())

    assert replica.bag is held
    assert held["gnr.a"] == 1
    assert "stale" not in held.keys()


def test_a_working_copy_captures_nothing_of_its_own_hydration() -> None:
    """The Phase 8 order, here too: hydrate the Bag first, attach the collector after."""
    master = CapturingGlobalStore()
    master.set("gnr.a", 1)
    master.drain()
    hydrated = from_tytx(master.snapshot(), "json")

    copy = CapturingGlobalStore(hydrated)

    assert copy.bag["gnr.a"] == 1
    assert copy.drain() == []
    copy.bag.set_item("gnr.b", 2)
    assert [change["key"]["path"] for change in copy.drain()] == ["gnr.b"]


# ----------------------------------------------------------------------
# The simple write: one writer above, one push per worker
# ----------------------------------------------------------------------


async def test_a_write_propagates_to_every_replica(pool: Stored) -> None:
    pool.sends.clear()

    assert await pool.store_set("alice", "gnr.a", 1) == {"path": "gnr.a"}

    await until(lambda: all(replica["gnr.a"] == 1 for replica in pool.replicas()))
    assert pool.commander.global_master.bag["gnr.a"] == 1
    # The author's own worker is pushed to like every other: one writer, one order.
    assert sorted((name, path) for name, path, _ in pool.sends) == sorted(
        (name, GLOBAL_CHANGES_PATH) for name in pool.names
    )


async def test_a_write_never_touches_the_authors_replica_by_itself(pool: Stored) -> None:
    """The op ascends and writes nothing locally — the replica waits for the push."""
    worker = pool.worker_of(0)
    pool.commander.assign_user("alice", pool.names[0])
    granted = asyncio.Event()
    propagate = pool.commander.propagate_global

    async def held_propagation() -> None:
        await granted.wait()
        await propagate()

    pool.commander.propagate_global = held_propagation  # type: ignore[method-assign]

    await pool.commander.forward_call("alice", "/op/store_set", {"path": "gnr.a", "value": 1})

    await until(lambda: pool.commander.global_master.collector.pending > 0)
    assert worker.global_store["gnr.a"] is None
    granted.set()
    await until(lambda: worker.global_store["gnr.a"] == 1)


async def test_a_delete_propagates_like_a_write(pool: Stored) -> None:
    await pool.store_set("alice", "gnr.a", 1)
    await until(lambda: all(replica["gnr.a"] == 1 for replica in pool.replicas()))

    assert await pool.store_del("alice", "gnr.a") == {"path": "gnr.a"}

    await until(lambda: all("a" not in replica["gnr"].keys() for replica in pool.replicas()))
    assert "a" not in pool.commander.global_master.bag["gnr"].keys()


async def test_a_worker_registers_with_an_aligned_replica(pool: Stored) -> None:
    await pool.store_set("alice", "gnr.a", 1)
    await until(lambda: all(replica["gnr.a"] == 1 for replica in pool.replicas()))
    pool.sends.clear()

    name = await pool.add_worker()

    newcomer = pool.workers[name]
    await until(lambda: newcomer.global_store["gnr.a"] == 1)
    assert [(sent_name, path) for sent_name, path, _ in pool.sends] == [
        (name, GLOBAL_SNAPSHOT_PATH)
    ]


# ----------------------------------------------------------------------
# The lock: the grant carries the master, the changes land at the release
# ----------------------------------------------------------------------


async def test_the_grant_carries_the_true_master_state(pool: Stored) -> None:
    await pool.store_set("alice", "gnr.a", 1)
    await until(lambda: pool.commander.global_master.bag["gnr.a"] == 1)
    worker = pool.worker_of(1)
    # Its replica is deliberately behind: the grant is what makes the copy true.
    worker.global_store.clear()

    async with worker.global_store_lock() as copy:
        assert copy["gnr.a"] == 1
        copy.set_item("gnr.b", 2)

    # The release propagated to every replica, this one included: the hole closes.
    await until(lambda: worker.global_store["gnr.b"] == 2)


async def test_the_release_applies_exactly_what_was_drained(pool: Stored) -> None:
    worker = pool.worker_of(0)

    async with worker.global_store_lock() as copy:
        copy.set_item("gnr.a", 1)
        copy.set_item("gnr.b", 2)
        # The world sees nothing while the lock is held.
        assert pool.commander.global_master.bag["gnr.a"] is None

    await until(lambda: all(replica["gnr.b"] == 2 for replica in pool.replicas()))
    assert pool.commander.global_master.bag["gnr.a"] == 1
    assert pool.commander.global_master.bag["gnr.b"] == 2


async def test_a_body_that_raises_applies_nothing(pool: Stored) -> None:
    """All-or-nothing is not only about death: an interrupted lock writes nothing."""
    worker = pool.worker_of(0)

    with pytest.raises(RuntimeError, match="halfway"):
        async with worker.global_store_lock() as copy:
            copy.set_item("gnr.a", 1)
            raise RuntimeError("halfway")

    await until(lambda: pool.commander.global_lock.holder is None)
    assert pool.commander.global_master.bag["gnr.a"] is None


async def test_the_waiters_are_served_in_order(pool: Stored) -> None:
    """The FIFO is ``asyncio.Lock``'s own: three holders, three sequential writes."""
    worker = pool.worker_of(0)
    order: list[int] = []

    async def hold(index: int) -> None:
        async with worker.global_store_lock() as copy:
            order.append(index)
            copy.set_item(f"gnr.k{index}", index)
            await asyncio.sleep(0.01)

    await hold(0)
    await asyncio.gather(*(hold(index) for index in (1, 2, 3)))

    assert order == [0, 1, 2, 3]
    await until(lambda: pool.commander.global_master.bag["gnr.k3"] == 3)
    master = pool.commander.global_master.bag
    assert [master[f"gnr.k{index}"] for index in range(4)] == [0, 1, 2, 3]


async def test_a_second_holder_sees_the_first_holders_changes(pool: Stored) -> None:
    """The grant is taken from the master AFTER the previous release applied."""
    worker = pool.worker_of(0)

    async with worker.global_store_lock() as copy:
        copy.set_item("gnr.a", 1)
    async with worker.global_store_lock() as copy:
        assert copy["gnr.a"] == 1
        copy.set_item("gnr.a", 2)

    await until(lambda: pool.commander.global_master.bag["gnr.a"] == 2)


async def test_the_sync_form_holds_the_lock_from_a_pool_thread(pool: Stored) -> None:
    """A sync op handler blocks its own thread on the grant — the 2a vehicle rule."""
    worker = pool.worker_of(0)

    def under_lock() -> Any:
        with worker.global_store_lock() as copy:
            copy.set_item("gnr.a", 1)
            return copy["gnr.a"]

    assert await worker.pool.run(under_lock) == 1
    await until(lambda: pool.commander.global_master.bag["gnr.a"] == 1)


async def test_a_dead_holder_releases_the_lock_with_the_master_untouched(pool: Stored) -> None:
    """No lease and no timer: the channel EOF is the whole death protocol."""
    worker = pool.worker_of(1)
    name = pool.names[1]
    await pool.store_set("alice", "gnr.a", 1)
    await until(lambda: pool.commander.global_master.bag["gnr.a"] == 1)

    lease = worker.global_store_lock()
    copy = await lease.__aenter__()
    copy.set_item("gnr.a", 99)
    assert pool.commander.global_lock.held_by(name)

    await pool.channels[name].close()

    await until(lambda: pool.commander.global_lock.holder is None)
    assert pool.commander.global_master.bag["gnr.a"] == 1
    # The lock is free again for the surviving worker.
    async with pool.worker_of(0).global_store_lock() as other:
        assert other["gnr.a"] == 1


async def test_a_waiter_that_died_parked_never_jams_the_lock(pool: Stored) -> None:
    """The death rule covers a parked waiter too: its won grant is undeliverable.

    A waiter's channel can end BEFORE it holds anything, so no ``channel_lost``
    will ever release it. When its parked acquire finally wins, the grant post
    finds the channel gone and the commander releases on the spot — the lock
    must reach the next living waiter instead of jamming forever.
    """
    holder = pool.worker_of(0)
    dead_name = pool.names[1]

    lease = holder.global_store_lock()
    await lease.__aenter__()
    parked = asyncio.create_task(pool.workers[dead_name].global_store_lock().__aenter__())
    await asyncio.sleep(0.05)  # let the store_lock CALL park on the commander FIFO
    assert not parked.done()

    await pool.channels[dead_name].close()
    await lease.__aexit__(None, None, None)

    # The dead waiter's grant is released at once; the lock is free again.
    await until(lambda: pool.commander.global_lock.holder is None)
    async with holder.global_store_lock() as copy:
        assert copy is not None
    parked.cancel()
    with pytest.raises(asyncio.CancelledError):
        await parked


async def test_a_release_of_a_grant_no_longer_in_force_applies_nothing(
    pool: Stored, caplog: Any
) -> None:
    """The death released it first; the release still on the wire must be inert."""
    commander = pool.commander
    name = pool.names[0]
    await commander.global_lock.acquire(name, "r1")
    commander.global_lock.release()

    with caplog.at_level("DEBUG", logger="genro_asgi.spa.commander"):
        await commander.release_global_lock(name, {"request_id": "r1", "changes": '"[]::X"'})

    assert "no longer in force" in caplog.text
    assert commander.global_master.bag.is_empty()
