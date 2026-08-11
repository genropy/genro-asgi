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
import time
from typing import Any

import pytest

from genro_asgi.channel.hub import ChannelCallError
from genro_asgi.spa.commander import (
    CONSUMPTION_BUCKET_SECONDS,
    CONSUMPTION_BUCKETS,
    LOGIN_OP,
    METRICS_WINDOW,
    TOMBSTONE_SECONDS,
    UserStickyCommander,
)


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
        commander.fold_events("W:w-1", [event("drop_pages", 1, user="alice")])
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


def test_a_child_that_never_registers_is_stillborn_and_buriable(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """No REGISTER means no channel_lost: the READY_TIMEOUT path must stamp the
    death itself, or the row sits in draining forever, unburiable."""
    commander.worker_roster["W:mute"] = commander.new_roster_row(999, None)
    commander.worker_roster["W:mute"]["spawned_at"] = (
        time.monotonic() - commander.READY_TIMEOUT - 1
    )
    with caplog.at_level("WARNING"):
        commander.reconcile()
    entry = commander.worker_roster["W:mute"]
    assert entry["status"] == "dead"
    assert entry["death"] == "stillborn"
    assert entry["died_at"] is not None
    entry["died_at"] = time.monotonic() - TOMBSTONE_SECONDS - 1
    commander.reconcile()
    assert "W:mute" not in commander.worker_roster


def test_retiring_a_nascent_worker_takes_the_stillborn_exit(
    commander: UserStickyCommander,
) -> None:
    """A nascent has no channel, so draining could never complete: whether the
    retirement comes from retire(), scale() or the cull, it dies on the spot —
    stamped, buriable, never a permanent draining row."""
    commander.worker_roster["W:new"] = commander.new_roster_row(999, None)
    commander.retire_worker("W:new")
    entry = commander.worker_roster["W:new"]
    assert entry["status"] == "dead"
    assert entry["death"] == "stillborn"
    assert entry["died_at"] is not None
    entry["died_at"] = time.monotonic() - TOMBSTONE_SECONDS - 1
    commander.reconcile()
    assert "W:new" not in commander.worker_roster


def test_retire_refuses_a_worker_that_is_not_living(commander: UserStickyCommander) -> None:
    """A tombstone flipped back to draining would be unburiable, and the target
    would shrink for a corpse: only nascent and active are retirable."""
    commander.target = 2
    commander.worker_roster["W:w-1"]["status"] = "dead"
    commander.worker_roster["W:w-2"]["status"] = "draining"
    for name in ("W:w-1", "W:w-2"):
        with pytest.raises(ValueError):
            commander.retire(name)
    assert commander.target == 2
    assert commander.worker_roster["W:w-1"]["status"] == "dead"
    assert commander.worker_roster["W:w-2"]["status"] == "draining"


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
# The surface tree: the edge sets and the labels say the same thing
# ----------------------------------------------------------------------


def assert_tree_aligned(commander: UserStickyCommander) -> None:
    """Every edge agrees with its label, and every label with its edge."""
    edges = {
        (user, session_id)
        for user, sessions in commander.user_connections.items()
        for session_id in sessions
    }
    assert edges == {(user, session_id) for session_id, user in commander.connection_user.items()}
    page_edges = {
        (session_id, page_id)
        for session_id, pages in commander.connection_pages.items()
        for page_id in pages
    }
    assert page_edges == {
        (connection, page_id) for page_id, connection in commander.page_connection.items()
    }
    assert all(sessions for sessions in commander.user_connections.values())
    assert all(pages for pages in commander.connection_pages.values())


def populate_tree(commander: UserStickyCommander) -> None:
    """Alice with two connections on ``W:w-1``, bob with one on ``W:w-2``."""
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_connection", 2, user="alice", session_id="s1"),
            event("new_page", 3, user="alice", page_id="p1", session_id="s1"),
            event("new_connection", 4, user="alice", session_id="s2"),
            event("new_page", 5, user="alice", page_id="p2", session_id="s2"),
            event("new_page", 6, user="alice", page_id="p3", session_id="s2"),
        ],
    )
    commander.fold_events(
        "W:w-2",
        [
            event("new_user", 1, user="bob"),
            event("new_connection", 2, user="bob", session_id="s9"),
            event("new_page", 3, user="bob", page_id="p9", session_id="s9"),
        ],
    )


def test_the_tree_is_aligned_after_a_full_lifecycle(commander: UserStickyCommander) -> None:
    populate_tree(commander)
    assert_tree_aligned(commander)

    assert commander.connections_of("alice") == ["s1", "s2"]
    assert commander.pages_of_connection("s2") == ["p2", "p3"]
    assert [commander.worker_of_page(page) for page in ("p1", "p2", "p3")] == ["W:w-1"] * 3


def test_removing_a_user_never_touches_a_sibling_user(commander: UserStickyCommander) -> None:
    populate_tree(commander)

    commander.remove_user("alice")

    assert_tree_aligned(commander)
    assert commander.user_connections == {"bob": {"s9"}}
    assert commander.connection_pages == {"s9": {"p9"}}
    assert commander.page_connection == {"p9": "s9"}


def test_a_login_moves_the_edge_and_orphans_nothing(commander: UserStickyCommander) -> None:
    populate_tree(commander)

    commander.fold_events(
        "W:w-2",
        [event(LOGIN_OP, 4, user="alice", previous_user="bob", session_id="s9", package="")],
    )

    assert_tree_aligned(commander)
    assert commander.connections_of("alice") == ["s1", "s2", "s9"]
    assert "bob" not in commander.user_connections
    # p9 came over with s9: its owner derives to alice without any page write.
    assert commander.page_connection == {"p1": "s1", "p2": "s2", "p3": "s2", "p9": "s9"}
    assert commander.connection_user["s9"] == "alice"


def test_dropping_a_connection_leaves_its_sibling_intact(commander: UserStickyCommander) -> None:
    populate_tree(commander)

    commander.fold_events(
        "W:w-1",
        [
            event("drop_page", 7, user="alice", page_id="p2"),
            event("drop_page", 8, user="alice", page_id="p3"),
            event("drop_connection", 9, user="alice", session_id="s2"),
        ],
    )

    assert_tree_aligned(commander)
    assert commander.user_connections["alice"] == {"s1"}
    assert commander.connection_pages["s1"] == {"p1"}
    assert "s2" not in commander.connection_pages


def test_discard_connection_edge_on_a_missing_set_raises(
    commander: UserStickyCommander,
) -> None:
    """A missing edge set is a broken surface: KeyError, never a silent pass."""
    with pytest.raises(KeyError):
        commander.discard_connection_edge("ghost", "s1")


def test_discard_page_edge_on_a_missing_set_raises(commander: UserStickyCommander) -> None:
    """The page twin holds the same contract as the connection edge."""
    with pytest.raises(KeyError):
        commander.discard_page_edge("ghost", "p1")


def test_a_malformed_event_is_an_explicit_error(commander: UserStickyCommander) -> None:
    """The worker shapes every event whole: a missing entity key raises at the fold."""
    with pytest.raises(KeyError):
        commander.fold_events("W:w-1", [event("new_page", 1, user="alice")])


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
    assert set(report) == {
        "worker",
        "users",
        "pages",
        "pending",
        "seq",
        "cpu",
        "rss",
        "reusable",
        "trim_s",
        "executor",
    }
    assert set(report["executor"]) == {"busy", "total"}


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
        await commander.member_joined(FakeMember(name))
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
        await pool.member_joined(FakeMember(name))
        born.append(pool.worker_roster[name]["caretaker"])
        await waited(names)

    monkeypatch.setattr(pool, "wait_workers_end", register_late)
    await pool.stop()
    assert born != [None]
    assert all(row["caretaker"] is None for row in pool.worker_roster.values())
    with pytest.raises(asyncio.CancelledError):
        await born[0]


# ----------------------------------------------------------------------
# The forward counters: per-worker cumulative, per-user consumption
# ----------------------------------------------------------------------


def answer(commander: UserStickyCommander, payload: dict[str, Any]) -> None:
    """Make every ``hub.call`` of this commander answer with *payload*."""

    async def call(worker: str, path: str, data: Any, timeout: Any = None) -> dict[str, Any]:
        return payload

    commander.hub.call = call  # type: ignore[method-assign]


def explode(commander: UserStickyCommander) -> None:
    """Make every ``hub.call`` of this commander raise before answering."""

    async def call(worker: str, path: str, data: Any, timeout: Any = None) -> dict[str, Any]:
        raise ChannelCallError("W:w-1", "/op", {"message": "boom"})

    commander.hub.call = call  # type: ignore[method-assign]


def test_count_forward_folds_requests_errors_and_seconds(
    commander: UserStickyCommander,
) -> None:
    commander.count_forward("W:w-1", 0.5)
    commander.count_forward("W:w-1", 0.25, error=True)
    assert commander.forward_counters["W:w-1"] == {
        "requests": 1,
        "errors": 1,
        "seconds": 0.75,
    }


def test_a_fresh_consumption_entry_is_a_fixed_ring_of_never_written_slots(
    commander: UserStickyCommander,
) -> None:
    entry = commander.new_consumption_entry()
    assert entry["requests"] == 0 and entry["seconds"] == 0.0
    assert len(entry["buckets"]) == CONSUMPTION_BUCKETS
    assert all(slot == {"epoch": -1, "requests": 0, "seconds": 0.0} for slot in entry["buckets"])


def test_consumption_accumulates_cumulatively_and_in_the_current_bucket(
    commander: UserStickyCommander,
) -> None:
    now = 1000.0
    commander.count_user_consumption("alice", 0.4, now=now)
    commander.count_user_consumption("alice", 0.6, now=now + 1.0)
    entry = commander.user_consumption["alice"]
    assert entry["requests"] == 2
    assert entry["seconds"] == pytest.approx(1.0)
    epoch = int(now // CONSUMPTION_BUCKET_SECONDS)
    slot = entry["buckets"][epoch % CONSUMPTION_BUCKETS]
    assert slot["epoch"] == epoch
    assert slot["requests"] == 2
    assert slot["seconds"] == pytest.approx(1.0)


def test_a_stale_slot_is_reset_before_the_forward_lands(
    commander: UserStickyCommander,
) -> None:
    """A slot the ring wrapped onto belongs to its new epoch alone."""
    span = CONSUMPTION_BUCKET_SECONDS * CONSUMPTION_BUCKETS
    commander.count_user_consumption("alice", 0.4, now=1000.0)
    commander.count_user_consumption("alice", 0.1, now=1000.0 + span)
    epoch = int((1000.0 + span) // CONSUMPTION_BUCKET_SECONDS)
    slot = commander.user_consumption["alice"]["buckets"][epoch % CONSUMPTION_BUCKETS]
    assert slot == {"epoch": epoch, "requests": 1, "seconds": pytest.approx(0.1)}
    assert commander.user_consumption["alice"]["requests"] == 2


def test_recent_seconds_sums_the_window_and_excludes_what_fell_out_of_it(
    commander: UserStickyCommander,
) -> None:
    now = 1000.0
    commander.count_user_consumption("alice", 0.4, now=now)
    commander.count_user_consumption("alice", 0.2, now=now + CONSUMPTION_BUCKET_SECONDS)
    assert commander.user_recent_seconds("alice", now=now + CONSUMPTION_BUCKET_SECONDS) == (
        pytest.approx(0.6)
    )
    later = now + CONSUMPTION_BUCKET_SECONDS * CONSUMPTION_BUCKETS
    assert commander.user_recent_seconds("alice", now=later) == pytest.approx(0.2)


def test_an_unknown_user_consumed_nothing(commander: UserStickyCommander) -> None:
    assert commander.user_recent_seconds("nobody") == 0.0


def test_forgetting_a_user_drops_its_consumption(commander: UserStickyCommander) -> None:
    commander.count_user_consumption("alice", 0.4, now=1000.0)
    commander.forget_users(["alice", "ghost"])
    assert commander.user_consumption == {}


async def test_a_forward_clocks_the_worker_and_the_user_it_belongs_to(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    answer(commander, {"result": 7})
    assert await commander.forward_call("alice", "/op") == 7
    counters = commander.forward_counters["W:w-1"]
    assert counters["requests"] == 1 and counters["errors"] == 0
    assert counters["seconds"] >= 0.0
    assert commander.user_consumption["alice"]["requests"] == 1


async def test_a_forward_of_an_unheld_identity_clocks_the_worker_only(
    commander: UserStickyCommander,
) -> None:
    """A guest the surface does not hold yet is not attributed a consumption."""
    answer(commander, {"result": 7})
    await commander.forward_call("guest", "/op")
    assert commander.forward_counters["W:w-1"]["requests"] == 1
    assert commander.user_consumption == {}


async def test_a_failed_forward_is_counted_as_an_error_and_re_raised(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    explode(commander)
    with pytest.raises(ChannelCallError):
        await commander.forward_call("alice", "/op")
    counters = commander.forward_counters["W:w-1"]
    assert counters["requests"] == 0 and counters["errors"] == 1
    assert commander.user_consumption == {}


async def test_the_login_fold_cannot_resurrect_the_guest_consumption(
    commander: UserStickyCommander,
) -> None:
    """Clock and attribution run BEFORE the fold (the legacy order): the guest
    the REPLY logs in is counted while the surface still holds it, then
    forgotten with it — never re-created after its own removal."""
    commander.fold_events("W:w-1", [event("new_user", 1, user="s-1")])
    answer(
        commander,
        {
            "result": 7,
            "events": [event(LOGIN_OP, 2, user="alice", previous_user="s-1", session_id="c-1")],
        },
    )
    assert await commander.forward_call("s-1", "/op") == 7
    assert "s-1" not in commander.user_consumption


async def test_a_removal_mid_flight_cannot_resurrect_the_consumption(
    commander: UserStickyCommander,
) -> None:
    """The membership is read at count time: an identity a concurrent fold
    removed while the forward was in flight is not billed back into existence
    (the orphan would be unreachable by forget_users forever)."""
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])

    async def call(worker: str, path: str, data: Any, timeout: Any = None) -> dict[str, Any]:
        commander.remove_user("alice")  # the concurrent fold lands mid-flight
        return {"result": 7}

    commander.hub.call = call  # type: ignore[method-assign]
    await commander.forward_call("alice", "/op")
    assert commander.user_consumption == {}


async def test_the_fold_runs_off_the_forward_clock(
    commander: UserStickyCommander,
) -> None:
    """During the REPLY fold the forward already stands in the ledger: the
    placement round trip of another user is never billed to this one."""
    commander.fold_events("W:w-1", [event("new_user", 1, user="s-1")])
    ledger_during_fold: list[dict[str, Any]] = []

    async def call(worker: str, path: str, data: Any, timeout: Any = None) -> dict[str, Any]:
        if path == "/op":
            login = event(
                LOGIN_OP, 2, user="alice", previous_user="s-1", session_id="c-1", package="pkg"
            )
            return {"result": 7, "events": [login]}
        # the placement leg of the fold: the forward must already be counted
        ledger_during_fold.append(dict(commander.forward_counters["W:w-1"]))
        return {"result": None}

    commander.hub.call = call  # type: ignore[method-assign]
    await commander.forward_call("s-1", "/op")
    assert ledger_during_fold and ledger_during_fold[0]["requests"] == 1


def test_the_archived_row_carries_the_counters_snapshot(
    commander: UserStickyCommander,
) -> None:
    """The snapshot is a copy: the counters that keep moving never rewrite it."""
    commander.count_forward("W:w-1", 0.5)
    commander.record_occupancy("W:w-1", {"users": 1})
    commander.count_forward("W:w-1", 0.5)
    row = commander.worker_roster["W:w-1"]["occupancy"][-1]
    assert row["forward"] == {"requests": 1, "errors": 0, "seconds": 0.5}


def test_a_worker_that_never_forwarded_archives_zeros(
    commander: UserStickyCommander,
) -> None:
    commander.record_occupancy("W:w-1", {"users": 0})
    row = commander.worker_roster["W:w-1"]["occupancy"][-1]
    assert row["forward"] == {"requests": 0, "errors": 0, "seconds": 0.0}


def test_retiring_a_worker_keeps_its_counters(commander: UserStickyCommander) -> None:
    """The ledger follows the roster rule: only the burial drops it, never the drain."""
    commander.count_forward("W:w-1", 0.5)
    commander.retire_worker("W:w-1")
    assert commander.forward_counters["W:w-1"]["requests"] == 1


async def test_the_death_is_stamped_on_the_tombstone(commander: UserStickyCommander) -> None:
    commander.worker_roster["W:w-1"]["status"] = "draining"
    await commander.channel_lost(FakeMember("W:w-1"))
    await commander.channel_lost(FakeMember("W:w-2"))
    retired, crashed = commander.worker_roster["W:w-1"], commander.worker_roster["W:w-2"]
    assert retired["status"] == crashed["status"] == "dead"
    assert retired["death"] == "retired"
    assert crashed["death"] == "crash"
    assert retired["died_at"] is not None and crashed["died_at"] is not None


def test_a_worker_dead_within_the_lapse_keeps_its_tombstone(
    commander: UserStickyCommander,
) -> None:
    commander.count_forward("W:w-1", 0.5)
    entry = commander.worker_roster["W:w-1"]
    entry["status"] = "dead"
    entry["death"] = "crash"
    entry["died_at"] = time.monotonic()
    commander.reconcile()
    assert "W:w-1" in commander.worker_roster
    assert "W:w-1" in commander.forward_counters


def test_a_worker_dead_past_the_lapse_is_buried_with_its_counters(
    commander: UserStickyCommander, caplog: Any
) -> None:
    """One exit for row and ledger; the obituary log line is the durable trace."""
    commander.count_forward("W:w-1", 0.5)
    entry = commander.worker_roster["W:w-1"]
    entry["status"] = "dead"
    entry["death"] = "crash"
    entry["died_at"] = time.monotonic() - TOMBSTONE_SECONDS - 1
    with caplog.at_level("INFO"):
        commander.reconcile()
    assert "W:w-1" not in commander.worker_roster
    assert "W:w-1" not in commander.forward_counters
    assert "buried" in caplog.text and "death=crash" in caplog.text
    # the living neighbour is untouched
    assert "W:w-2" in commander.worker_roster


def test_removing_a_user_forgets_its_consumption(commander: UserStickyCommander) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    commander.count_user_consumption("alice", 0.4, now=1000.0)
    commander.remove_user("alice")
    assert commander.user_consumption == {}


def test_sweeping_a_worker_forgets_the_consumption_of_its_users(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events("W:w-1", [event("new_user", 1, user="alice")])
    commander.fold_events("W:w-2", [event("new_user", 1, user="bob")])
    commander.count_user_consumption("alice", 0.4, now=1000.0)
    commander.count_user_consumption("bob", 0.4, now=1000.0)
    commander.sweep_worker("W:w-1")
    assert set(commander.user_consumption) == {"bob"}
