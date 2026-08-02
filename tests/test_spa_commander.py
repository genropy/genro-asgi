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

"""Commander tests: the fold on its own, then real children on a real hub.

The fold and the surface registries are pure bookkeeping and are asserted
without a process in sight. Supervision is not: readiness, death and the
fresh-name relaunch only mean something against children that really run, so
the second half spawns ``python -m genro_asgi.spa.worker_entry`` for real and
kills them.
"""

from __future__ import annotations

import asyncio
import re
import signal
from typing import Any

import pytest

from genro_asgi.spa.commander import METRICS_WINDOW, UserStickyCommander


async def swallow_frame(frame: Any) -> None:
    """A member face that reads every frame and answers none."""

SPAWN_TIMEOUT = 15.0


def event(op: str, seq: int, **payload: Any) -> dict[str, Any]:
    """One shaped lifecycle event as a worker would offer it."""
    return {"op": op, "seq": seq, **payload}


class DeadProcess:
    """The ``Popen`` surface reconcile reads: a child that already exited."""

    def __init__(self, code: int) -> None:
        self.pid = 999
        self.code = code

    def poll(self) -> int:
        return self.code


class LiveProcess:
    """The ``Popen`` surface supervision reads: a child that is still running."""

    def __init__(self) -> None:
        self.pid = 999

    def poll(self) -> None:
        return None


class FakeMember:
    """The ``ChannelMember`` surface the callbacks read: just the name."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.pid = 0


@pytest.fixture
def commander(tmp_path: Any) -> UserStickyCommander:
    """A commander with two enrolled workers and a hub that is never started."""
    running = UserStickyCommander(workers=0, path=str(tmp_path / "hub.sock"))
    for name in ("W:w-1", "W:w-2"):
        running.worker_roster[name] = running.new_roster_row(0, None)
        running.worker_roster[name]["status"] = "active"
    return running


async def until(predicate: Any, timeout: float = SPAWN_TIMEOUT) -> None:
    """Await a condition without blocking the loop."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise TimeoutError("condition never became true")
        await asyncio.sleep(0.02)


# ----------------------------------------------------------------------
# The fold and the surface registries
# ----------------------------------------------------------------------


def test_new_user_maps_the_user_to_the_announcing_worker(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    assert commander.user_worker_map == {"alice": "W:w-1"}
    assert commander.users_on("W:w-1") == {"alice"}
    assert commander.worker_roster["W:w-1"]["group"] == "default"


def test_drop_user_unmaps_it(commander: UserStickyCommander) -> None:
    commander.fold_events(
        "W:w-1", [event("new_user", 1, user="alice"), event("drop_user", 2, user="alice")]
    )
    assert commander.user_worker_map == {}
    assert commander.users_on("W:w-1") == set()


def test_a_seq_already_seen_is_folded_again(commander: UserStickyCommander) -> None:
    """No dedup: the envelope is causal, so every event it carries is applied."""
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    commander.fold_events("W:w-1", [event("drop_user", 1, user="alice")])
    assert commander.user_worker_map == {}


def test_events_are_folded_in_the_order_they_were_delivered(
    commander: UserStickyCommander,
) -> None:
    """The seq is a diagnostic stamp, not an ordering gate: the list order rules."""
    commander.fold_events(
        "W:w-1", [event("drop_user", 2, user="alice"), event("new_user", 1, user="alice")]
    )
    assert commander.user_worker_map == {"alice": "W:w-1"}


def test_a_late_event_never_re_points_an_assigned_user(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    commander.fold_events("W:w-2", [event("new_user", 1, user="alice")])
    assert commander.user_worker_map == {"alice": "W:w-1"}


def test_a_foreign_drop_leaves_the_owner_alone(commander: UserStickyCommander) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    commander.fold_events("W:w-2", [event("drop_user", 1, user="alice")])
    assert commander.user_worker_map == {"alice": "W:w-1"}


def test_assign_user_is_the_explicit_decision_above_the_owner_check(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    commander.assign_user("alice", "W:w-2")
    assert commander.user_worker_map == {"alice": "W:w-2"}


def test_a_reserved_lifecycle_op_has_no_surface_consumer_yet(
    commander: UserStickyCommander, caplog: Any
) -> None:
    with caplog.at_level("WARNING"):
        commander.fold_events("W:w-1", [event("new_page", 1, user="alice")])
    assert commander.user_worker_map == {}
    assert caplog.records == []


def test_an_unknown_op_is_a_warning(commander: UserStickyCommander, caplog: Any) -> None:
    with caplog.at_level("WARNING"):
        commander.fold_events("W:w-1", [event("teleport_user", 1, user="alice")])
    assert "teleport_user" in caplog.text


def test_sweeping_a_worker_forgets_its_users_but_keeps_the_row(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    commander.fold_events("W:w-2", [event("new_user", 1, user="bob")])
    assert commander.sweep_worker("W:w-1") == ["alice"]
    assert commander.user_worker_map == {"bob": "W:w-2"}
    assert commander.users_on("W:w-1") == set()


def test_the_occupancy_window_keeps_the_last_reports_only(
    commander: UserStickyCommander,
) -> None:
    for n in range(METRICS_WINDOW + 5):
        commander.record_occupancy("W:w-1", {"users": n})
    window = commander.worker_roster["W:w-1"]["occupancy"]
    assert len(window) == METRICS_WINDOW
    assert window[-1]["report"] == {"users": METRICS_WINDOW + 4}


def test_a_worker_name_is_a_fresh_uuid_every_time(commander: UserStickyCommander) -> None:
    minted = [commander.next_worker_name() for _ in range(3)]
    assert len(set(minted)) == 3
    assert all(re.fullmatch(r"W:[0-9a-f]{32}", name) for name in minted)


def test_a_child_that_dies_before_registering_is_logged_with_its_exit_code(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """No backoff any more: the death is recorded and the next tick respawns."""
    commander.worker_roster["W:w-3"] = commander.new_roster_row(999, DeadProcess(3))
    with caplog.at_level("WARNING"):
        commander.reconcile()
    assert "exit code 3" in caplog.text
    assert commander.worker_roster["W:w-3"]["status"] == "dead"


async def test_a_deliberate_retire_sweeps_the_users_it_held(
    commander: UserStickyCommander,
) -> None:
    """A retired worker holds nothing either: its users must leave the surface."""
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    commander.worker_roster["W:w-1"]["status"] = "draining"
    await commander.channel_lost(FakeMember("W:w-1"))
    assert commander.user_worker_map == {}
    assert commander.users_on("W:w-1") == set()
    # Alice is a guest again, and another worker may legitimately claim her.
    assert commander.worker_for("alice") == "W:w-2"
    commander.fold_events("W:w-2", [event("new_user", 1, user="alice")])
    assert commander.user_worker_map == {"alice": "W:w-2"}


def test_retiring_an_unknown_worker_is_an_error(commander: UserStickyCommander) -> None:
    with pytest.raises(KeyError, match="no such worker"):
        commander.retire("W:ghost")


# ----------------------------------------------------------------------
# Supervision — real children on a real UDS hub
# ----------------------------------------------------------------------


@pytest.fixture
async def pool() -> Any:
    """A commander with a fast heartbeat, stopped (and reaped) at teardown."""
    running = UserStickyCommander(
        workers=0, worker_kwargs={"max_threads": 2}
    )
    await running.start()
    try:
        yield running
    finally:
        await running.stop()


@pytest.fixture
async def watched_pool() -> Any:
    """A pool whose caretakers visit their worker several times a second."""
    running = UserStickyCommander(
        workers=0, worker_kwargs={"max_threads": 2}, probe_interval=0.05
    )
    await running.start()
    try:
        yield running
    finally:
        await running.stop()


async def test_scale_brings_the_pool_up_to_two_active_workers(pool: Any) -> None:
    pool.scale(2)
    await pool.wait_workers_ready(2)
    assert len(pool.active_workers) == 2
    for name in pool.active_workers:
        entry = pool.worker_roster[name]
        assert entry["status"] == "active"
        assert entry["pid"] == entry["process"].pid
        assert entry["group"] == "default"


async def test_a_call_creates_the_user_and_its_reply_folds_the_map(pool: Any) -> None:
    pool.scale(1)
    await pool.wait_workers_ready(1)
    name = pool.active_workers[0]
    payload = await pool.hub.call(name, "/op/new_user", {"identity": "alice", "kwargs": {}})
    await pool.unwrap_reply(name, "/op/new_user", payload)
    assert payload["result"]["register_item_id"] == "alice"
    assert pool.user_worker_map == {"alice": name}


async def test_a_killed_worker_is_swept_and_relaunched_with_a_fresh_name(pool: Any) -> None:
    pool.scale(1)
    await pool.wait_workers_ready(1)
    doomed = pool.active_workers[0]
    await pool.unwrap_reply(
        doomed,
        "/op/new_user",
        await pool.hub.call(doomed, "/op/new_user", {"identity": "alice", "kwargs": {}}),
    )
    assert pool.user_worker_map == {"alice": doomed}
    pool.worker_roster[doomed]["process"].kill()
    await until(lambda: pool.worker_roster[doomed]["status"] == "dead")
    assert pool.user_worker_map == {}
    await pool.wait_workers_ready(1)
    assert pool.active_workers != [doomed]


async def test_the_caretaker_archives_the_report_the_worker_answered(
    watched_pool: Any,
) -> None:
    """Nobody calls the probe: the worker's own caretaker visits it and files the reading."""
    watched_pool.scale(1)
    await watched_pool.wait_workers_ready(1)
    name = watched_pool.active_workers[0]
    assert watched_pool.worker_roster[name]["caretaker"] is not None
    await until(lambda: bool(watched_pool.worker_roster[name]["occupancy"]))
    report = watched_pool.worker_roster[name]["occupancy"][-1]["report"]
    assert report["worker"] == name
    assert set(report) == {"worker", "users", "pages", "pending", "seq"}


async def test_a_caretaker_survives_a_probe_that_raises(
    watched_pool: Any, monkeypatch: Any
) -> None:
    """The blast radius of a failed visit is that visit: the cadence goes on."""
    watched_pool.scale(1)
    await watched_pool.wait_workers_ready(1)
    name = watched_pool.active_workers[0]
    archived = watched_pool.record_occupancy
    visits: list[str] = []

    def explode_once(worker: str, report: dict[str, Any]) -> None:
        visits.append(worker)
        if len(visits) == 1:
            raise RuntimeError("the archive refused this reading")
        archived(worker, report)

    monkeypatch.setattr(watched_pool, "record_occupancy", explode_once)
    watched_pool.worker_roster[name]["occupancy"].clear()
    await until(lambda: bool(watched_pool.worker_roster[name]["occupancy"]))
    assert len(visits) >= 2


async def test_a_caretaker_kills_the_worker_that_never_answers(monkeypatch: Any) -> None:
    """The one CALL with a deadline: silence is the answer, and the task acts on it."""
    commander = UserStickyCommander(
        workers=0, local_worker=True, probe_interval=0.02, probe_timeout=0.05
    )
    await commander.start()
    name = commander.worker.name
    row = commander.worker_roster[name]
    killed: list[tuple[str, int]] = []
    monkeypatch.setattr(commander, "signal_worker", lambda n, sig: killed.append((n, sig)))
    try:
        # A caretaker is born only for a row with a real process: give the
        # in-process worker a live one and replay its REGISTER.
        row["process"] = LiveProcess()
        commander.member_joined(FakeMember(name))
        # The member is on the wire and reads the CALL — and answers nothing.
        commander.local_channel.on_message = swallow_frame
        await until(lambda: bool(killed), timeout=5.0)
        assert killed[0] == (name, signal.SIGKILL)
        assert not row["occupancy"]
    finally:
        commander.cancel_caretaker(name)
        row["process"] = None
        await commander.stop()


async def test_retire_lowers_the_target_so_nothing_is_relaunched(pool: Any) -> None:
    pool.scale(2)
    await pool.wait_workers_ready(2)
    victim = pool.active_workers[0]
    pool.retire(victim)
    await until(lambda: pool.worker_roster[victim]["status"] == "dead")
    assert pool.target == 1
    await asyncio.sleep(pool.RECONCILE_INTERVAL * 3)
    assert len(pool.living_workers) == 1
    assert victim not in pool.living_workers


async def test_a_deliberate_stop_leaves_no_worker_behind(pool: Any) -> None:
    pool.scale(2)
    await pool.wait_workers_ready(2)
    processes = [pool.worker_roster[n]["process"] for n in pool.active_workers]
    await pool.stop()
    assert pool.living_workers == []
    assert all(process.poll() is not None for process in processes)


async def test_a_member_joining_mid_stop_leaves_no_caretaker_behind(
    pool: Any, monkeypatch: Any
) -> None:
    """The final sweep is airtight: a caretaker born during the stop is still ended.

    A late REGISTER landing while ``stop()`` waits for the retired children
    re-activates the row and births a fresh caretaker; only a sweep AFTER the
    hub is closed can catch it, because no ``channel_lost`` will ever cancel it.
    """
    name = "W:late"
    pool.worker_roster[name] = pool.new_roster_row(999, DeadProcess(0))
    waited = pool.wait_workers_end
    born: list[Any] = []

    async def register_late(names: list[str]) -> None:
        pool.member_joined(FakeMember(name))
        born.append(pool.worker_roster[name]["caretaker"])
        await waited(names)

    monkeypatch.setattr(pool, "wait_workers_end", register_late)
    await pool.stop()
    assert born != [None]
    assert all(row["caretaker"] is None for row in pool.worker_roster.values())
    with pytest.raises(asyncio.CancelledError):
        await born[0]
