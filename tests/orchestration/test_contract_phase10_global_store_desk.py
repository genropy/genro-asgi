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

"""Phase 10 contract: the global store lives only on the commander.

The ratified digression (registro 2026-08-20 §7-bis): no replicas on the
workers — verified fact: the 22-name site contract never reads the global store
directly, it only touches it through ``store_set``, ``store_del`` and the copy
``global_store_lock`` grants. Every access is a CALL on the phase-7 lane, with
an immediate REPLY. The lock is the pre_refactoring protocol carried over: the
grant brings the master's copy, the release applies the drained changes —
full-shape (attributes, reason, fired), so nothing is lost on the way up.

Derived from ``tests/test_spa_global_store.py``, the original contract of that
protocol; what the envelope mechanics of the executed phase 5 added (replicas,
old_value, the writes slot) dies with this phase.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, SpaCommander
from genro_asgi.spa.orchestration import spa_commander as spa_commander_module
from genro_asgi.spa.orchestration import spa_worker as spa_worker_module
from genro_asgi.spa.orchestration import worker_connector as worker_connector_module

from .conftest import WORKER_NAME, XT_DeskLane, wait_for

SECOND_WORKER_NAME = "standard_0002"


@pytest.fixture
async def second_lane(desk_lane, tmp_path):
    """A second worker on the same desk: what a FIFO grant needs two of."""
    lane = XT_DeskLane(
        desk_lane.commander,
        desk_lane.worker_handler.group_handler,
        FreezeHandler(tmp_path / "frozen_users_second"),
        worker_name=SECOND_WORKER_NAME,
    )
    await lane.open()
    yield lane
    await lane.close()


async def test_store_set_lands_on_the_master_before_it_answers(desk_lane):
    # wf:contract: store_set(identity, path, value=) is a CALL on the lane;
    # wf:contract: when it returns {"path": path}, the commander's master
    # wf:contract: already holds the value — no replica anywhere, no waiting
    # wf:contract: for any later push.
    answer = await desk_lane.verb("store_set", "alice", "gnr.a", value=1)

    assert answer == {"path": "gnr.a"}
    assert desk_lane.commander.global_register["gnr.a"] == 1


async def test_store_del_removes_the_node_rather_than_nulling_it(desk_lane):
    # wf:contract: after store_del returns, the master's node is GONE — not
    # wf:contract: None — exactly the pre_refactoring delete semantics.
    await desk_lane.verb("store_set", "alice", "gnr.a", value=1)
    await desk_lane.verb("store_set", "alice", "gnr.b", value=2)

    answer = await desk_lane.verb("store_del", "alice", "gnr.a")

    assert answer == {"path": "gnr.a"}
    assert desk_lane.commander.global_register["gnr.a"] is None
    assert desk_lane.commander.global_register["gnr"].keys() == ["b"]


async def test_the_grant_carries_the_true_master_state(desk_lane):
    # wf:contract: global_store_lock's acquire answers with the master's own
    # wf:contract: copy at grant time — a worker that never saw any state reads
    # wf:contract: the current truth from the copy, no staleness question.
    desk_lane.commander.global_register.set_item("gnr.a", 12)

    async with desk_lane.worker.global_store_lock() as copy:
        assert copy["gnr.a"] == 12


async def test_the_release_applies_exactly_what_was_drained_in_full_shape(desk_lane):
    # wf:contract: changes made on the granted copy land on the master only at
    # wf:contract: the release, attributes and reason included; while the lock
    # wf:contract: is held the master shows nothing of them.
    master = desk_lane.commander.global_register
    master.set_item("gnr.a", 12)

    async with desk_lane.worker.global_store_lock() as copy:
        copy.set_item("gnr.a", copy["gnr.a"] * 2, _attributes={"tag": "recount"})
        assert master["gnr.a"] == 12

    assert master["gnr.a"] == 24
    assert master.get_attr("gnr.a") == {"tag": "recount"}


async def test_a_body_that_raises_applies_nothing(desk_lane):
    # wf:contract: a lock body that raises releases with nothing applied — the
    # wf:contract: all-or-nothing of the pre_refactoring lease.
    master = desk_lane.commander.global_register
    master.set_item("gnr.a", 1)

    with pytest.raises(RuntimeError, match="the site fell over"):
        async with desk_lane.worker.global_store_lock() as copy:
            copy.set_item("gnr.a", 99)
            raise RuntimeError("the site fell over")

    assert master["gnr.a"] == 1
    # And the grant is back: the next hold is served.
    async with desk_lane.worker.global_store_lock() as copy:
        assert copy["gnr.a"] == 1


async def test_the_waiters_are_served_in_order_and_see_the_previous_release(
    desk_lane, second_lane
):
    # wf:contract: a second holder's grant is taken from the master AFTER the
    # wf:contract: first holder's release applied: FIFO, read-modify-write safe.
    master = desk_lane.commander.global_register
    master.set_item("gnr.a", 1)
    granted = asyncio.Event()
    release_now = asyncio.Event()
    second_read: list[int] = []

    async def first_holder() -> None:
        async with desk_lane.worker.global_store_lock() as copy:
            granted.set()
            copy.set_item("gnr.a", copy["gnr.a"] + 10)
            await release_now.wait()

    async def second_holder() -> None:
        async with second_lane.worker.global_store_lock() as copy:
            second_read.append(copy["gnr.a"])

    first = asyncio.create_task(first_holder())
    await granted.wait()
    second = asyncio.create_task(second_holder())

    # The second's call is on the wire and unanswered: it is parked on the grant,
    # which the first still holds.
    await wait_for(lambda: bool(second_lane.worker._parent_calls))
    assert second_read == []

    release_now.set()
    await asyncio.gather(first, second)

    assert second_read == [11]
    assert master["gnr.a"] == 11


async def test_a_dead_holders_lock_is_released_with_the_master_untouched(
    desk_lane, second_lane
):
    # wf:contract: the holder's channel ending releases the lock without
    # wf:contract: applying its half-made changes; the next waiter gets a clean
    # wf:contract: grant — the pre_refactoring death rule, on the new lane.
    commander = desk_lane.commander
    commander.global_register.set_item("gnr.a", 1)
    working = await desk_lane.worker.acquire_global_lock("hold-1")
    working.bag.set_item("gnr.a", 99)

    assert commander.global_lock.held_by(WORKER_NAME) is True

    desk_lane.worker_handler.on_child_lost()

    assert commander.global_lock.holder is None
    assert commander.global_register["gnr.a"] == 1
    async with second_lane.worker.global_store_lock() as copy:
        assert copy["gnr.a"] == 1


async def test_the_replica_machinery_is_gone(desk_lane):
    # wf:contract: SpaWorker holds no global replica and no queued writes; no
    # wf:contract: envelope slot carries the global store in either direction;
    # wf:contract: old_value exists nowhere — the phase-5 envelope mechanics
    # wf:contract: are fully removed with their tests rewritten (foreman
    # wf:contract: decision, notes.md).
    for gone in ("GLOBAL_STORE_KEY", "GLOBAL_WRITES_KEY", "ENVELOPE_SLOT_GLOBAL_STORE"):
        assert not hasattr(worker_connector_module, gone)
    for gone in (
        "global_replica",
        "global_register_item_tytx",
        "record_global_write",
        "_global_writes",
        "_take_global_store",
    ):
        assert not hasattr(desk_lane.worker, gone)
    # `global_store` exists again since 2026-08-20, as the READ-ONLY published
    # view (owner decision) — a view is not a replica: nothing rides envelopes.
    assert not hasattr(SpaCommander, "apply_global_writes")

    written = "".join(
        Path(module.__file__).read_text()
        for module in (spa_worker_module, spa_commander_module, worker_connector_module)
    )
    assert "old_value" not in written
    assert "global_replica" not in written
