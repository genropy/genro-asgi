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

"""The freezer: an idle user hibernates into a file, and comes back out of it.

The mechanism only — the planner's freeze rung is a later phase, so every
freeze here is ordered by hand. The pool is the same in-process one the move
tests drive, so a parcel really crosses ``freeze_user`` on a worker, really
lands in a file, and really comes back through the ordinary ``add_user``
handover.

The valve — how long a user must sit idle before it is due — is read off the
``pool_occupancy`` worlds, where memory pressure and idle ages are exactly what
the fixture says they are.

No test ever names a real directory: ``frozen_users_dir`` is always a tmp_path.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import pytest
from genro_storage import StorageNode

from genro_asgi.spa.commander import FROZEN, UserStickyCommander

from .test_spa_move import (
    LocalPool,
    PageWorker,
    enroll,
    frozen_node,
    seed_live_guest,
    settled_at,
)


@pytest.fixture
async def freezing(tmp_path: Path) -> Any:
    """A two-worker pool with the freezer armed on a directory of its own."""
    running = LocalPool(
        worker_class=PageWorker,
        freeze_idle_after=1800.0,
        frozen_users_dir=frozen_node(tmp_path / "frozen"),
    )
    await running.start(2)
    try:
        yield running
    finally:
        await running.stop()


async def a_frozen_alice(pool: Any) -> Any:
    """Seed a live user with one page, freeze it, and return its parcel node."""
    await seed_live_guest(pool, pool.commander.reception)
    await pool.commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await settled_at(pool.commander, "alice", pool.commander.reception)
    assert await pool.commander.freeze_user("alice")
    return pool.commander.frozen_users_dir.child("alice")


# ----------------------------------------------------------------------
# The parcel: what freezing writes, and what it leaves behind
# ----------------------------------------------------------------------


async def test_a_frozen_user_leaves_a_parcel_and_a_frozen_placement(freezing: Any) -> None:
    """The slice goes to a file, the placement becomes the FROZEN state, and the
    worker that held it holds it no more — while the rows below the user, its
    connection and its page, stay exactly where they were."""
    commander = freezing.commander
    worker = commander.reception
    parcel = await a_frozen_alice(freezing)
    assert parcel.exists()
    assert commander.user_worker_map["alice"] == FROZEN
    assert "alice" not in commander.worker_roster[worker]["users"]
    assert freezing.workers[worker].user_items.get("alice") is None
    # The surface keeps the user's own tree: it is hibernating, not gone.
    assert commander.connection_user["sess-1"] == "alice"
    assert commander.page_connection["p1"] == "sess-1"
    # And no half-written parcel is ever left in the directory.
    assert sorted(node.basename for node in parcel.parent.children()) == ["alice"]


async def test_a_user_nobody_holds_is_not_frozen(freezing: Any) -> None:
    """Freezing answers what it did, and a user off the surface — or already in
    the freezer — is not frozen twice."""
    commander = freezing.commander
    assert not await commander.freeze_user("nobody-knows-me")
    await a_frozen_alice(freezing)
    assert not await commander.freeze_user("alice")


async def test_a_frozen_user_is_not_routed_without_being_woken(freezing: Any) -> None:
    """``worker_for`` is the sync question and a frozen user has no answer to it:
    serving it at the reception would seat it as a guest while its slice waits
    in a file, so the seam says so instead."""
    commander = freezing.commander
    await a_frozen_alice(freezing)
    with pytest.raises(RuntimeError, match="frozen"):
        commander.worker_for("alice")


# ----------------------------------------------------------------------
# The wake: the next request, and the login that carries the file
# ----------------------------------------------------------------------


async def test_the_next_request_of_a_frozen_user_wakes_it_and_serves_it(freezing: Any) -> None:
    """The whole point: a frozen user's next call resolves through the wake and
    is served where the parcel landed, with its page alive again — and the spent
    parcel is DELETED, so the directory holds only what is still hibernating."""
    commander = freezing.commander
    parcel = await a_frozen_alice(freezing)
    envelope = await commander.forward_envelope("alice", "/op/page_ping", {"page_id": "p1"})
    assert envelope["result"]["page_id"] == "p1"
    destination = commander.user_worker_map["alice"]
    assert destination in freezing.workers
    assert freezing.workers[destination].page_items.get("p1") is not None
    assert not parcel.exists()
    assert parcel.parent.children() == []


async def test_two_requests_arriving_together_wake_the_parcel_once(freezing: Any) -> None:
    """The wake raises the move barrier synchronously, so the second request
    parks on it instead of installing the same parcel a second time."""
    commander = freezing.commander
    await a_frozen_alice(freezing)
    both = await asyncio.gather(
        commander.resolve_worker("alice"), commander.resolve_worker("alice")
    )
    assert both[0] == both[1] == commander.user_worker_map["alice"]


async def test_a_login_carries_the_parcel_to_the_worker_it_arrived_on(freezing: Any) -> None:
    """The cookie expired, so the user comes back as a guest and logs in: the
    login finds the parcel and wakes it onto the worker the fresh connection is
    already open on, where ``add_user`` joins the two."""
    commander = freezing.commander
    await a_frozen_alice(freezing)
    target = commander.reception
    await commander.forward_call("sess-9", "/op/new_connection")
    await commander.forward_call("sess-9", "/op/change_connection_user", {"user": "alice"})
    await settled_at(commander, "alice", target)
    # The page that went into the freezer with the old connection is alive again
    # on the worker the new one is open on, joined to what the login just made.
    assert freezing.workers[target].page_items.get("p1") is not None
    assert not commander.frozen_users_dir.child("alice").exists()


async def test_a_login_never_wakes_a_parcel_the_map_has_no_placement_for(
    freezing: Any,
) -> None:
    """The wake trigger is the MAP, not the disk: a commander with no ``FROZEN``
    placement for alice — restarted since the hibernation, or a parcel the reaper
    has not reached — logs her in as the stranger she now is, and the orphan file
    is never delivered over the live entry the login just made."""
    await a_frozen_alice(freezing)
    reborn = LocalPool(
        worker_class=PageWorker,
        freeze_idle_after=1800.0,
        frozen_users_dir=freezing.commander.frozen_users_dir,
    )
    await reborn.start(1)
    try:
        commander = reborn.commander
        assert "alice" not in commander.user_worker_map
        await commander.forward_call("sess-9", "/op/new_connection")
        await commander.forward_call("sess-9", "/op/change_connection_user", {"user": "alice"})
        await settled_at(commander, "alice", commander.reception)
        # A fresh slice, with nothing of the hibernation in it — and the orphan
        # parcel still on disk, waiting for nothing but the reaper.
        assert commander.page_connection.get("p1") is None
        assert commander.frozen_users_dir.child("alice").exists()
    finally:
        await reborn.stop()


async def test_the_login_wake_claims_the_barrier_before_its_task_detaches(freezing: Any) -> None:
    """The login's wake runs detached, so the hold has to be up the instant the
    fold's tick ends: a request arriving before the task's first step would find
    a FROZEN placement with nothing raised and install the same parcel twice."""
    commander = freezing.commander
    await a_frozen_alice(freezing)
    target = str(commander.reception)
    commander.settle_login(target, "alice", "sess-9", None)
    # Synchronous: no await has run between the settle and this assertion.
    assert commander.is_held("alice")
    await settled_at(commander, "alice", target)
    assert not commander.is_held("alice")


async def test_a_request_in_the_login_wake_window_parks_instead_of_waking_twice(
    freezing: Any,
) -> None:
    """The race the hold closes: a request landing while the login's wake is still
    detached parks on the barrier and is served where the login put the parcel —
    one install, one spent parcel, no second wake finding nothing."""
    commander = freezing.commander
    await a_frozen_alice(freezing)
    target = commander.reception
    commander.settle_login(target, "alice", "sess-9", None)
    assert await commander.resolve_worker("alice") == target
    assert commander.user_worker_map["alice"] == target
    assert not commander.frozen_users_dir.child("alice").exists()


async def test_a_login_landing_mid_wake_leaves_the_barrier_to_its_owner(
    freezing: Any, caplog: Any
) -> None:
    """The other side of the same hold: a wake already in flight OWNS the barrier,
    and a login landing while the placement still reads FROZEN must not replace it
    — a request parked on the old Event would wait for a wake nobody raised. The
    login spawns nothing, says so loudly, and the wake in flight finishes."""
    commander = freezing.commander
    await a_frozen_alice(freezing)
    target = commander.reception
    holds: list[Any] = []
    decide = commander.decide_worker

    def login_while_the_wake_is_choosing() -> str:
        holds.append(commander.moving["alice"])
        commander.settle_login(target, "alice", "sess-9", None)
        holds.append(commander.moving["alice"])
        return decide()

    commander.decide_worker = login_while_the_wake_is_choosing  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING):
        assert await commander.resolve_worker("alice") == target
    commander.decide_worker = decide  # type: ignore[method-assign]
    assert holds[0] is holds[1]  # the wake's own Event, never swapped out
    assert any("found a hold already up" in record.getMessage() for record in caplog.records)
    assert commander.user_worker_map["alice"] == target
    assert not commander.is_held("alice")
    assert not commander.frozen_users_dir.child("alice").exists()


async def test_a_user_whose_parcel_expired_comes_back_as_a_stranger(freezing: Any) -> None:
    """A FROZEN placement with no parcel is not impossible — the reaper outlived
    the hibernation, or the file went by hand. The wake clears the placement and
    the rows under it and answers False, so the next request is SERVED at the
    reception instead of failing for as long as the commander lives."""
    commander = freezing.commander
    parcel = await a_frozen_alice(freezing)
    parcel.delete()
    assert await commander.resolve_worker("alice") == commander.reception
    assert "alice" not in commander.user_worker_map
    assert "sess-1" not in commander.connection_user
    assert "p1" not in commander.page_connection


async def test_the_reaper_deletes_the_parcel_and_touches_no_placement(
    freezing: Any, tmp_path: Path
) -> None:
    """The reaper is pure housekeeping: the expired file goes, the FROZEN entry
    pointing at it stays exactly where it is, and the wake's own expired branch —
    the one implementation of expiry there is — clears it at the next request,
    which is served."""
    commander = freezing.commander
    parcel = await a_frozen_alice(freezing)
    os.utime(tmp_path / "frozen" / "alice", (0.0, 0.0))
    commander.reap_frozen_files()
    assert not parcel.exists()
    assert commander.user_worker_map["alice"] == FROZEN
    assert await commander.resolve_worker("alice") == commander.reception
    assert "alice" not in commander.user_worker_map
    assert "p1" not in commander.page_connection


async def test_a_parcel_that_will_not_unpickle_wakes_its_user_as_a_stranger(
    freezing: Any, caplog: Any
) -> None:
    """Writing the parcel straight to its name leaves a half-write window, and
    this is the loud end of it: a truncated file cannot be a slice, so the wake
    takes the same road as an expired one — WARNING, the wedge cleared, the user
    served as the stranger it now is, and the unusable file off the disk."""
    commander = freezing.commander
    parcel = await a_frozen_alice(freezing)
    whole = parcel.read_text()
    parcel.write_text(whole[: len(whole) // 2])
    with caplog.at_level(logging.WARNING):
        assert await commander.resolve_worker("alice") == commander.reception
    assert any("is missing or unreadable" in record.getMessage() for record in caplog.records)
    assert not parcel.exists()
    assert "alice" not in commander.user_worker_map
    assert "p1" not in commander.page_connection


# ----------------------------------------------------------------------
# The custody: nothing is destroyed on the way to the file
# ----------------------------------------------------------------------


async def test_a_directory_that_refuses_writes_drops_the_user_loudly(
    freezing: Any, tmp_path: Path, caplog: Any
) -> None:
    """A freezer pointed at somewhere unwritable is an operations mistake, and a
    storage node carries no writability question to ask in advance: it is
    discovered AT the write, past the seal, so the freeze ends on the loud road
    — ERROR, the user off the surface, the next contact starting it clean."""
    commander = freezing.commander
    source = commander.reception
    await seed_live_guest(freezing, source)
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await settled_at(commander, "alice", source)
    real_dir = tmp_path / "frozen"
    real_dir.mkdir(parents=True, exist_ok=True)
    real_dir.chmod(0o500)
    try:
        with caplog.at_level(logging.ERROR):
            assert not await commander.freeze_user("alice")
    finally:
        real_dir.chmod(0o700)
    assert any("comes back as a stranger" in record.getMessage() for record in caplog.records)
    assert "alice" not in commander.user_worker_map
    assert "p1" not in commander.page_connection


async def test_a_write_that_fails_after_the_seal_drops_the_user_loudly(
    freezing: Any, monkeypatch: Any, caplog: Any
) -> None:
    """The disk filled between the question and the write — an operations matter,
    not a case this code recovers from. The slice is already off its worker, so
    the freeze says so at ERROR and takes the user off the surface: no orphan
    mapping pointing at a worker that let the slice go, and the next contact
    starts it clean, as a stranger."""
    commander = freezing.commander
    source = commander.reception
    await seed_live_guest(freezing, source)
    await commander.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await settled_at(commander, "alice", source)
    original_write = StorageNode.write_text

    def the_disk_fills_between(self: Any, *args: Any, **kwargs: Any) -> Any:
        if self.basename == "alice":
            raise OSError(28, "No space left on device")
        return original_write(self, *args, **kwargs)

    monkeypatch.setattr(StorageNode, "write_text", the_disk_fills_between)
    with caplog.at_level(logging.ERROR):
        assert not await commander.freeze_user("alice")
    monkeypatch.undo()
    assert any("comes back as a stranger" in record.getMessage() for record in caplog.records)
    assert "alice" not in commander.user_worker_map
    assert "p1" not in commander.page_connection
    assert commander.worker_for("alice") == source


@pytest.mark.parametrize("identity", ["tenant/alice", "../escapee", "rossi\\mario"])
async def test_any_identity_freezes_under_its_userkey(tmp_path: Path, identity: str) -> None:
    """An identity carrying separators is nobody's exemption: ``user_to_userkey``
    flattens it into a plain filename INSIDE the freezer directory, so the user
    is a candidate like any other and its parcel is found where it was filed."""
    armed = UserStickyCommander(
        workers=0,
        path=str(tmp_path / "hub.sock"),
        freeze_idle_after=1.0,
        frozen_users_dir=frozen_node(tmp_path / "frozen"),
    )
    enroll(armed, "W:w-1")
    armed.assign_user(identity, "W:w-1")
    armed.worker_roster["W:w-1"]["users"][identity]["last_activity_ts"] = 0.0
    assert (identity, "W:w-1") in armed.freeze_candidates
    userkey = armed.user_to_userkey(identity)
    assert "/" not in userkey and "\\" not in userkey and userkey not in ("", ".", "..")
    armed.frozen_users_dir.mkdir(parents=True)
    armed.frozen_users_dir.child(userkey).write_text("a parcel")
    assert [node.basename for node in armed.frozen_users_dir.children()] == [userkey]


# ----------------------------------------------------------------------
# The hibernated store: on a wake, the parcel is the truth
# ----------------------------------------------------------------------


async def test_the_hibernated_store_survives_the_login_that_wakes_it(freezing: Any) -> None:
    """Friday to Monday: a user with preferences in its store hibernates, the
    cookie expires over the weekend, and the login that brings it back makes a
    fresh entry an instant before the parcel lands. Days of state must not yield
    to that instant — the carried store wins, and the preferences are still
    there."""
    commander = freezing.commander
    target = commander.reception
    await a_frozen_alice(freezing)
    await commander.forward_call("sess-9", "/op/new_connection")
    await commander.forward_call("sess-9", "/op/change_connection_user", {"user": "alice"})
    await settled_at(commander, "alice", target)
    assert freezing.workers[target].user_items.get("alice")["store"]["prefs.theme"] == "dark"


async def test_the_store_the_parcel_brings_takes_its_watchers_with_it(freezing: Any) -> None:
    """The swap is not a rebinding of a name: a page of the resident was already
    watching the entry's old Bag, and it has to end up watching the arrived one —
    with whatever it had captured still pending. Otherwise the user reads the
    hibernated store while its open page reports changes to a Bag nobody writes."""
    commander = freezing.commander
    target = commander.reception
    parcel = await a_frozen_alice(freezing)
    # The resident the login makes an instant before the parcel lands, with a
    # page of its own already subscribed to the store prefix.
    worker = freezing.workers[target]
    worker.registry.new_connection("sess-9", user="alice")
    worker.registry.new_page("p9", user="alice", connection_id="sess-9")
    worker.registry.subscribe_store_path("p9", "prefs")
    resident_store = worker.user_items.get("alice")["store"]
    resident_store["prefs.theme"] = "light"
    pending_before = len(worker.page_items.get("p9")["user_view"].changes)
    await commander.hand_user_to(target, "alice", parcel.read_text(), parcel_wins=True)
    adopted = worker.user_items.get("alice")["store"]
    assert adopted is not resident_store
    assert adopted["prefs.theme"] == "dark"
    view = worker.page_items.get("p9")["user_view"]
    assert len(view.changes) == pending_before
    adopted["prefs.lang"] = "it"
    assert [change["key"]["path"] for change in view.changes[pending_before:]] == ["prefs.lang"]


# ----------------------------------------------------------------------
# The valve: how long a user sits idle before it is due
# ----------------------------------------------------------------------


def test_the_candidates_are_the_users_past_the_effective_idle(
    occupancy_world: Any, tmp_path: Path
) -> None:
    """``loaded_pool``: alice idles 3600s on a worker at half pressure (effective
    idle 900s) and is due; bob idles 120s on a worker at 0.95 (effective idle is
    the 300s floor) and is not."""
    commander = occupancy_world(
        "loaded_pool", freeze_idle_after=1800.0, frozen_users_dir=frozen_node(tmp_path / "frozen")
    )
    assert commander.freeze_candidates == [("alice", "W:w-1")]


def test_the_valve_shortens_the_wait_as_the_memory_fills(
    occupancy_world: Any, tmp_path: Path
) -> None:
    """The same world, the same idle ages: bob's 120s only becomes due when the
    floor comes under it, which is what the pressure on his worker is asking
    for. The wait is ``freeze_idle_after × (1 - pressure)``, never under the
    floor — at 0.95 pressure, 2000s of nominal wait is 100s of real wait."""
    commander = occupancy_world(
        "loaded_pool",
        freeze_idle_after=2000.0,
        freeze_idle_floor=10.0,
        frozen_users_dir=frozen_node(tmp_path / "frozen"),
    )
    # alice: 2000 × 0.5 = 1000s, and she has idled 3600. bob: 2000 × 0.05 = 100s
    # against his 120. Longest idle first.
    assert commander.freeze_candidates == [("alice", "W:w-1"), ("bob", "W:w-2")]


def test_the_floor_keeps_a_barely_idle_user_out_of_the_freezer(
    occupancy_world: Any, tmp_path: Path
) -> None:
    """The same pressure, the stock floor: 300s is the shortest wait there is, so
    bob's 120s stays under it however full his worker gets."""
    commander = occupancy_world(
        "loaded_pool",
        freeze_idle_after=2000.0,
        freeze_idle_floor=300.0,
        frozen_users_dir=frozen_node(tmp_path / "frozen"),
    )
    assert [user for user, _ in commander.freeze_candidates] == ["alice"]


def test_a_disarmed_freezer_has_no_candidates(occupancy_world: Any) -> None:
    """``freeze_idle_after=None`` is the off switch: nobody is ever due, however
    long they have been idle."""
    commander = occupancy_world("loaded_pool")
    assert commander.freeze_idle_after is None
    assert commander.freeze_candidates == []


def test_a_user_with_work_in_flight_is_never_a_candidate(tmp_path: Path) -> None:
    """Idle age alone is not enough: a user with a live call is mid-conversation,
    and ``pool_occupancy`` leaves it out of the reading the valve reads."""
    armed = UserStickyCommander(
        workers=0,
        path=str(tmp_path / "hub.sock"),
        freeze_idle_after=1.0,
        frozen_users_dir=frozen_node(tmp_path / "frozen"),
    )
    enroll(armed, "W:w-1")
    armed.assign_user("alice", "W:w-1")
    armed.worker_roster["W:w-1"]["users"]["alice"]["last_activity_ts"] = 0.0
    assert armed.freeze_candidates == [("alice", "W:w-1")]
    armed.open_request("W:w-1", "alice", "/op/page_ping")
    assert armed.freeze_candidates == []


def test_arming_the_freezer_without_a_directory_is_refused(tmp_path: Path) -> None:
    """No instance name reaches this layer, so a parcel directory cannot be
    derived: an armed freezer with nowhere to write says so at construction
    rather than guessing a shared one."""
    with pytest.raises(ValueError, match="frozen_users_dir"):
        UserStickyCommander(workers=0, path=str(tmp_path / "hub.sock"), freeze_idle_after=1800.0)
