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

"""The early CPU growth of #43: the latch, the soft admission, the fallback, the wake.

The stage is the one ``test_orchestration_group_handler`` builds — real child
processes under a real group and a real vertex — and the CPU is DECLARED, not
burned: ``cpu_percent`` is written straight into the photo the handler holds,
which is exactly the field the judge reads. Implementation tests: they
photograph the experimental policy and go with it. This file replaced the
photograph of the one-shot preference when the Hetzner bench proved that
preference a fixed point at two workers (2026-08-28): the soft admission —
a worker over ``cpu_grow_percent`` is closed to NEW users until it falls
below ``cpu_grow_rearm_percent`` — is what these tests photograph now.
"""

from __future__ import annotations

import asyncio
import time as real_time

import pytest

from genro_asgi.spa.orchestration import AssignmentRefused
from genro_asgi.spa.orchestration import group_handler as group_handler_module
from genro_asgi.spa.orchestration.group_policy import GroupPolicyError

from .conftest import kill_process, wait_for

# The stage of the group tests, reused whole: the scripted child, the vertex,
# the group builder. Imported names are pytest fixtures and their dependencies.
from .test_orchestration_group_handler import (
    MEMORY_CEILING,
    WORKER_CEILING,
    known_at_the_vertex,
)
from .test_orchestration_group_handler import commander  # noqa: F401
from .test_orchestration_group_handler import group_settings  # noqa: F401
from .test_orchestration_group_handler import instance_root  # noqa: F401
from .test_orchestration_group_handler import make_group  # noqa: F401

ORDERS_LOGGER = "genro_asgi.orchestration.orders"


async def grown_group(make_group, **policies):
    """One group with the policy on, its reception unreserved as the experiment runs it."""
    policies.setdefault("reception_reserved_percent", 0.0)
    group = make_group(cpu_grow_percent=50.0, **policies)
    await group.start_worker()
    return group


def declare_cpu(worker_handler, cpu_percent: float) -> None:
    """Write the smoothed CPU into the photo the judge reads."""
    worker_handler.worker_snapshot["cpu_percent"] = cpu_percent


class ControlledTime:
    """The clock of the retirement quiet, advanced by hand — no real waiting.

    Stands in for the ``time`` module INSIDE group_handler only: ``monotonic``
    answers this clock, everything else is the real module — the workers, the
    envelope layer and asyncio keep the real time, so a test advancing the
    quiet moves no timer but the group's own.
    """

    def __init__(self) -> None:
        self.now = real_time.monotonic()

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __getattr__(self, name):
        return getattr(real_time, name)


@pytest.fixture
def group_clock(monkeypatch):
    """group_handler's clock, controlled: advance() is the only way it moves."""
    clock = ControlledTime()
    monkeypatch.setattr(group_handler_module, "time", clock)
    return clock


def arrival(commander, group, user: str):
    """One new user known at the vertex, ready for this group's placement."""
    known_at_the_vertex(commander, f"c_{user}", user)
    return group.assign_user(user)


# --- the soft admission and the latch ---------------------------------------


async def test_under_the_threshold_nothing_grows_and_admission_stays_open(make_group):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 49.9)

    await group.check_occupancy(now=True)

    assert len(group.worker_handler_map) == 1
    assert group.reception.cpu_admission_open is True


async def test_a_crossing_blocks_the_worker_and_grows_once(make_group, caplog):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)

    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        await group.check_occupancy(now=True)

    assert len(group.worker_handler_map) == 2
    assert group.reception.cpu_admission_open is False
    assert group.reception.cpu_growth_armed is False
    rows = [record.getMessage() for record in caplog.records]
    assert any("cpu_admission" in row and "blocked" in row for row in rows)
    assert any(
        "cpu_grow" in row and "grown standard_0002" in row and "spawn_seconds" in row
        for row in rows
    )


async def test_cpu_past_the_restart_setpoint_grows_without_restarting(make_group):
    group = await grown_group(make_group)
    original = group.reception
    declare_cpu(original, 96.0)

    await group.check_occupancy(now=True)

    assert original.name in group.worker_handler_map
    assert original.state == "running"
    assert original.cpu_admission_open is False
    assert sorted(group.worker_handler_map) == ["standard_0001", "standard_0002"]


async def test_snapshots_that_stay_above_the_threshold_are_one_crossing(make_group):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)

    for _ in range(3):
        await group.check_occupancy(now=True)

    assert len(group.worker_handler_map) == 2
    assert group.reception.cpu_admission_open is False


async def test_inside_the_hysteresis_band_the_state_is_kept(make_group):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)

    for cpu_percent in (45.0, 49.0, 41.0, 49.9):
        declare_cpu(group.reception, cpu_percent)
        await group.check_occupancy(now=True)

    assert group.reception.cpu_admission_open is False
    assert group.reception.cpu_growth_armed is False
    assert len(group.worker_handler_map) == 2


async def test_below_the_rearm_threshold_the_worker_reopens_and_rearms(make_group, caplog):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)

    declare_cpu(group.reception, 39.0)
    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        await group.check_occupancy(now=True)

    assert group.reception.cpu_admission_open is True
    assert group.reception.cpu_growth_armed is True
    assert "reopened" in caplog.text
    assert len(group.worker_handler_map) == 2


async def test_a_new_crossing_after_the_rearm_grows_again(make_group):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    declare_cpu(group.reception, 39.0)
    await group.check_occupancy(now=True)

    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)

    assert len(group.worker_handler_map) == 3


async def test_with_the_policy_off_a_burning_worker_changes_nothing(make_group, commander):
    # 60 is over the experimental threshold and under the admission ceiling:
    # with the policy off, NO road reads it as a reason to grow or to close.
    group = make_group(reception_reserved_percent=0.0)
    await group.start_worker()
    declare_cpu(group.reception, 60.0)

    await group.check_occupancy(now=True)

    assert len(group.worker_handler_map) == 1
    assert group.reception.cpu_growth_armed is True
    assert group.reception.cpu_admission_open is True
    assert await arrival(commander, group, "walkin") == "standard_0001"


# --- the placement over the admission ----------------------------------------


async def test_a_new_user_lands_on_the_open_worker_not_the_blocked_fullest(
    make_group, commander
):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)
    # The reception is the FULLEST by far and blocked; the newborn is open.
    assert await arrival(commander, group, "first") == "standard_0002"


async def test_the_newborn_takes_new_users_for_as_long_as_the_trigger_stays_hot(
    make_group, commander
):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)

    homes = [await arrival(commander, group, f"user{i}") for i in range(4)]

    assert homes == ["standard_0002"] * 4


async def test_two_open_workers_are_still_fullest_first(make_group, commander):
    group = await grown_group(make_group)
    second = await group.start_worker()
    declare_cpu(group.reception, 30.0)
    declare_cpu(second, 10.0)
    group.reception.worker_snapshot["rss_bytes"] = int(0.3 * WORKER_CEILING)

    assert await arrival(commander, group, "walkin") == "standard_0001"


async def test_sticky_users_stay_on_the_blocked_worker(make_group, commander):
    group = await grown_group(make_group)
    await arrival(commander, group, "resident")
    declare_cpu(group.reception, 60.0)

    await group.check_occupancy(now=True)

    assert group.user_worker_map["resident"] == "standard_0001"


async def test_the_newborn_crossing_fathers_the_third_and_takes_over(make_group, commander):
    # The whole desired sequence, end to end: worker 1 crosses -> blocked ->
    # worker 2 born -> consecutive users land on 2 -> worker 2 crosses ->
    # blocked -> worker 3 born -> new users on 3 -> sticky untouched.
    group = await grown_group(make_group)
    await arrival(commander, group, "resident")
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)
    assert sorted(group.worker_handler_map) == ["standard_0001", "standard_0002"]

    assert await arrival(commander, group, "second_a") == "standard_0002"
    assert await arrival(commander, group, "second_b") == "standard_0002"

    second = group.worker_handler_map["standard_0002"]
    declare_cpu(second, 55.0)
    await group.check_occupancy(now=True)
    assert sorted(group.worker_handler_map) == [
        "standard_0001",
        "standard_0002",
        "standard_0003",
    ]
    assert second.cpu_admission_open is False

    assert await arrival(commander, group, "third_a") == "standard_0003"
    assert await arrival(commander, group, "third_b") == "standard_0003"
    assert group.user_worker_map["resident"] == "standard_0001"
    assert group.user_worker_map["second_a"] == "standard_0002"


async def test_nobody_open_and_growth_allowed_births_the_capacity(make_group, commander):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)
    second = group.worker_handler_map["standard_0002"]
    declare_cpu(second, 60.0)
    await group.check_occupancy(now=True)
    # Both living workers are now blocked; the placement's own level 2 births.
    for worker_handler in group.living_workers:
        worker_handler.cpu_admission_open = False

    home = await arrival(commander, group, "walkin")

    assert home not in ("standard_0001", "standard_0002")
    assert len(group.worker_handler_map) >= 3


async def test_nobody_open_and_growth_refused_falls_back_on_a_blocked_worker(
    make_group, commander, caplog
):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)
    for worker_handler in group.living_workers:
        worker_handler.cpu_admission_open = False
    commander.state = "quitting"  # the growth is refused: _may_grow is False

    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        home = await arrival(commander, group, "walkin")
    commander.state = "running"

    assert home in ("standard_0001", "standard_0002")
    assert "placement_fallback" in caplog.text
    assert "over the soft limit" in caplog.text


async def test_a_blocked_worker_at_the_hard_limit_still_refuses(make_group, commander):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 85.0)  # over occupancy_max_percent: the hard gate
    await group.check_occupancy(now=True)
    group.drop_worker("standard_0002")  # only the hot reception remains
    group.reception.cpu_admission_open = False
    commander.state = "quitting"

    known_at_the_vertex(commander, "c_walkin", "walkin")
    with pytest.raises(AssignmentRefused):
        await group.assign_user("walkin")
    commander.state = "running"


async def test_the_fallback_is_never_used_while_an_open_worker_admits(
    make_group, commander, caplog
):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)

    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        home = await arrival(commander, group, "walkin")

    assert home == "standard_0002"
    assert "placement_fallback" not in caplog.text


async def test_worker_max_users_still_gates_the_open_worker(make_group, commander):
    group = await grown_group(make_group, worker_max_users=1)
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)

    first = await arrival(commander, group, "one")
    second = await arrival(commander, group, "two")

    assert first == "standard_0002"
    assert second not in ("standard_0001", "standard_0002")  # 2 is full BY HEADS, 1 blocked


# --- concurrency --------------------------------------------------------------


async def test_two_concurrent_rounds_cannot_fork_twice_for_one_event(make_group, caplog):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)

    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        await asyncio.gather(
            group.check_occupancy(now=True), group.check_occupancy(now=True)
        )

    assert len(group.worker_handler_map) == 2
    assert "suppressed" in caplog.text


async def test_a_crossing_and_a_placement_race_to_one_spawn(make_group, commander):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 60.0)
    known_at_the_vertex(commander, "c_arriving", "arriving")

    _, home = await asyncio.gather(
        group.check_occupancy(now=True), group.assign_user("arriving")
    )

    assert len(group.worker_handler_map) == 2
    assert home == "standard_0002"


async def test_the_reactive_growth_and_a_placement_cannot_fork_twice(make_group, commander):
    group = make_group(reception_reserved_percent=0.0)
    await group.start_worker()
    group.reception.worker_snapshot["rss_bytes"] = int(0.79 * WORKER_CEILING)
    known_at_the_vertex(commander, "c_arriving", "arriving")

    _, home = await asyncio.gather(
        group.check_occupancy(now=True), group.assign_user("arriving")
    )

    assert len(group.worker_handler_map) == 2
    assert home == "standard_0002"
    assert group.user_worker_map["arriving"] == "standard_0002"


async def test_two_workers_over_the_threshold_are_one_spawn_per_round(make_group):
    group = await grown_group(make_group)
    second = await group.start_worker()
    declare_cpu(group.reception, 60.0)
    declare_cpu(second, 60.0)

    await group.check_occupancy(now=True)
    assert len(group.worker_handler_map) == 3
    assert group.reception.cpu_admission_open is False
    assert second.cpu_admission_open is False

    # The second armed crossing is served by the NEXT round, one at a time.
    await group.check_occupancy(now=True)
    assert len(group.worker_handler_map) == 4


async def test_a_blocked_worker_that_dies_takes_its_state_with_it(make_group, commander):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)
    newborn = group.worker_handler_map["standard_0002"]
    declare_cpu(newborn, 60.0)
    await group.check_occupancy(now=True)
    third = group.worker_handler_map["standard_0003"]

    group.drop_worker("standard_0002")

    assert "standard_0002" not in group.worker_handler_map
    assert await arrival(commander, group, "walkin") == "standard_0003"

    kill_process(newborn.process)
    await wait_for(lambda: not newborn.process.alive)
    await newborn.connector.stop()
    assert third.state == "running"


async def test_a_failed_spawn_leaves_the_fallback_available(make_group, commander, caplog):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 60.0)
    await group.check_occupancy(now=True)
    for worker_handler in group.living_workers:
        worker_handler.cpu_admission_open = False
    group.worker_settings["worker_kwargs"]["behaviour"] = "absent"

    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        home = await arrival(commander, group, "walkin")

    assert home in ("standard_0001", "standard_0002")
    assert "placement_fallback" in caplog.text
    group.worker_settings["worker_kwargs"]["behaviour"] = "answer"


async def test_memory_refusing_the_growth_is_no_503_while_a_blocked_worker_has_room(
    make_group, commander, caplog
):
    group = await grown_group(
        make_group,
        memory_max_percent=10.0,
        # The worker's own ceiling is kept WIDE: only the group quota refuses
        # here, the worker itself stays under its hard admission limit.
        worker_memory_max_percent=400.0,
        # No restart here: the occupancy is clamped to 100 and never exceeds it.
        restart_occupancy_max_percent=100.0,
        rss_bytes=int(0.2 * MEMORY_CEILING),
    )
    declare_cpu(group.reception, 60.0)
    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        await group.check_occupancy(now=True)
    assert len(group.worker_handler_map) == 1  # the quota refused the growth
    assert "suppressed: the quota or the server state refuses the growth" in caplog.text

    home = await arrival(commander, group, "walkin")

    assert home == "standard_0001"


async def test_permission_that_falls_while_waiting_for_the_lock_stops_the_spawn(
    make_group, commander, caplog
):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)

    await group._placement_lock.acquire()
    round_task = asyncio.create_task(group.check_occupancy(now=True))
    for _ in range(5):
        await asyncio.sleep(0)
    commander.state = "quitting"
    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        group._placement_lock.release()
        await round_task
    commander.state = "running"

    assert len(group.worker_handler_map) == 1
    assert group.reception.cpu_growth_armed is True
    assert "suppressed: the quota or the server state refuses the growth" in caplog.text


async def test_a_trigger_worker_that_died_while_waiting_grows_nothing(
    make_group, commander, caplog
):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)

    await group._placement_lock.acquire()
    round_task = asyncio.create_task(group.check_occupancy(now=True))
    for _ in range(5):
        await asyncio.sleep(0)
    group.reception.state = "quitted"
    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        group._placement_lock.release()
        await round_task

    assert len(group.worker_handler_map) == 1
    assert "suppressed: the trigger worker is gone" in caplog.text


# --- the event-driven wake -----------------------------------------------------


async def test_a_photo_crossing_above_rings_the_wake(make_group):
    group = await grown_group(make_group)
    group.ping_now_event.clear()

    group.reception.envelope_handler.on_worker_snapshot({"cpu_percent": 55.0})

    assert group.ping_now_event.is_set()
    assert len(group.worker_handler_map) == 1  # the wake decided NOTHING


async def test_a_plateau_already_judged_rings_nothing(make_group):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)  # judged: the reception is blocked now
    group.ping_now_event.clear()

    group.reception.envelope_handler.on_worker_snapshot({"cpu_percent": 60.0})

    assert not group.ping_now_event.is_set()


async def test_with_the_policy_off_no_photo_rings_the_cpu_wake(make_group):
    group = make_group(reception_reserved_percent=0.0)
    await group.start_worker()
    group.ping_now_event.clear()

    group.reception.envelope_handler.on_worker_snapshot({"cpu_percent": 99.0})

    assert not group.ping_now_event.is_set()


async def test_the_descent_below_the_rearm_threshold_rings_the_wake(make_group):
    group = await grown_group(make_group)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    group.ping_now_event.clear()

    group.reception.envelope_handler.on_worker_snapshot({"cpu_percent": 35.0})
    assert group.ping_now_event.is_set()

    # Judged reopened, a NEW crossing rings again: a fresh plateau, not a storm.
    declare_cpu(group.reception, 35.0)
    await group.check_occupancy(now=True)
    group.ping_now_event.clear()
    group.reception.envelope_handler.on_worker_snapshot({"cpu_percent": 55.0})
    assert group.ping_now_event.is_set()


async def test_the_band_between_the_thresholds_rings_nothing(make_group):
    group = await grown_group(make_group)
    group.ping_now_event.clear()

    group.reception.envelope_handler.on_worker_snapshot({"cpu_percent": 45.0})

    assert not group.ping_now_event.is_set()


# --- the retirement stands apart ----------------------------------------------


async def test_the_newborn_is_not_retired_by_the_next_round(make_group):
    group = await grown_group(make_group, worker_min_life_seconds=60.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    declare_cpu(group.reception, 5.0)

    await group.check_occupancy(now=True)

    assert len(group.worker_handler_map) == 2


async def test_after_the_descent_and_the_quiet_the_spare_worker_is_released(
    make_group, group_clock
):
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=60.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    newborn = group.worker_handler_map["standard_0002"]

    # The load is gone: the reception reopens — a CPU event, the quiet restarts.
    declare_cpu(group.reception, 5.0)
    declare_cpu(newborn, 1.0)
    await group.check_occupancy(now=True)
    assert newborn.state == "running"  # suspended: the reopen just spoke

    group_clock.advance(61.0)
    await group.check_occupancy(now=True)  # the quiet elapsed: judged as always

    assert newborn.state in ("quitting", "quitted")


async def test_no_spawn_close_spawn_cycle_without_new_load(make_group, group_clock):
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=60.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    newborn = group.worker_handler_map["standard_0002"]

    declare_cpu(group.reception, 5.0)
    declare_cpu(newborn, 1.0)
    await group.check_occupancy(now=True)  # reopen: the quiet restarts
    group_clock.advance(61.0)
    for _ in range(4):
        await group.check_occupancy(now=True)
        group_clock.advance(61.0)

    assert len(group.worker_handler_map) == 2  # the spare quit, nobody respawned
    assert newborn.state in ("quitting", "quitted")


async def test_the_thresholds_must_leave_a_hysteresis_band(make_group):
    for grow, rearm in ((50.0, 60.0), (50.0, 50.0), (110.0, 40.0), (50.0, -1.0)):
        with pytest.raises(ValueError, match="hysteresis"):
            make_group(cpu_grow_percent=grow, cpu_grow_rearm_percent=rearm)

    make_group(cpu_grow_percent=50.0, cpu_grow_rearm_percent=40.0)
    make_group(cpu_grow_rearm_percent=60.0)  # policy off: the band is nobody's business


# --- the retirement stands aside while the CPU speaks ---------------------------


async def test_policy_off_keeps_the_retirement_immediate(make_group):
    # No CPU policy: the gate does not exist and the spare quits at once,
    # exactly as it always did — no cooldown appears from anywhere.
    group = make_group(reception_reserved_percent=0.0, cpu_retirement_quiet_seconds=3600.0)
    await group.start_worker()
    second = await group.start_worker()
    declare_cpu(group.reception, 1.0)
    declare_cpu(second, 1.0)

    await group.check_occupancy(now=True)

    assert second.state in ("quitting", "quitted")


async def test_policy_off_ignores_even_a_fresh_pressure_stamp(make_group):
    # The gate is inert with the policy off: a timestamp left by a policy that
    # was on — or by an apply that switched it off — holds nothing back.
    group = make_group(reception_reserved_percent=0.0, cpu_retirement_quiet_seconds=3600.0)
    await group.start_worker()
    second = await group.start_worker()
    declare_cpu(group.reception, 1.0)
    declare_cpu(second, 1.0)
    group.record_cpu_pressure()

    await group.check_occupancy(now=True)

    assert second.state in ("quitting", "quitted")


async def test_policy_on_from_boot_imposes_no_artificial_cooldown(make_group):
    # Policy ON, a huge quiet, and NO CPU event ever — no blocked, grown,
    # refusal or reopened: the pressure clock is still None, both workers are
    # open, and the FIRST check retires the spare as always. Distinct from the
    # policy-off test: here the gate exists and answers None.
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=3600.0)
    second = await group.start_worker()
    declare_cpu(group.reception, 1.0)
    declare_cpu(second, 1.0)
    assert group._cpu_pressure_monotonic is None
    assert group.reception.cpu_admission_open and second.cpu_admission_open

    await group.check_occupancy(now=True)

    assert second.state in ("quitting", "quitted")


async def test_a_cpu_closed_worker_suspends_the_retirement(make_group):
    # Even with a zero quiet, standing demand — a worker still closed — is
    # its own gate: the emptiest worker is not handed back to the hot one.
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=0.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    newborn = group.worker_handler_map["standard_0002"]
    declare_cpu(newborn, 1.0)
    declare_cpu(group.reception, 45.0)  # in the band: stays blocked

    await group.check_occupancy(now=True)

    assert newborn.state == "running"
    assert group.reception.cpu_admission_open is False


async def test_a_fresh_growth_holds_the_retirement_for_the_whole_quiet(
    make_group, group_clock
):
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=60.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)  # blocked + grown: pressure spoke
    newborn = group.worker_handler_map["standard_0002"]
    declare_cpu(group.reception, 5.0)
    declare_cpu(newborn, 1.0)
    await group.check_occupancy(now=True)  # reopen: restarts the quiet

    group_clock.advance(59.0)
    await group.check_occupancy(now=True)  # still inside the quiet

    assert newborn.state == "running"


async def test_a_quota_refused_growth_is_pressure_too(
    make_group, commander, group_clock, caplog
):
    # A crossing the group cannot honour is UNMET demand: the retirement must
    # not eat the capacity that demand is waiting for.
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=60.0)
    second = await group.start_worker()
    declare_cpu(group.reception, 60.0)
    declare_cpu(second, 1.0)
    commander.state = "saturated"  # _may_grow says no: the growth is refused

    with caplog.at_level("INFO", logger=ORDERS_LOGGER):
        await group.check_occupancy(now=True)  # crossing, growth refused

    assert "suppressed: the quota or the server state refuses the growth" in caplog.text
    group_clock.advance(59.0)
    declare_cpu(group.reception, 45.0)  # the band: still blocked, but even if...
    group.reception.cpu_admission_open = True  # ...nobody is closed any more
    await group.check_occupancy(now=True)

    assert second.state == "running"  # the refused demand still holds the quiet


async def test_a_reopen_restarts_the_whole_quiet(make_group, group_clock):
    # The measured churn defect: a worker closed for LONGER than the quiet,
    # then reopened — the retirement must not meet it at the very next beat.
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=60.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    newborn = group.worker_handler_map["standard_0002"]
    declare_cpu(newborn, 1.0)

    group_clock.advance(120.0)  # closed for two whole quiets: pressure is old
    declare_cpu(group.reception, 5.0)
    await group.check_occupancy(now=True)  # THIS round reopens the reception

    assert group.reception.cpu_admission_open is True
    assert newborn.state == "running"  # and closes nobody: the quiet restarted

    group_clock.advance(59.0)
    await group.check_occupancy(now=True)
    assert newborn.state == "running"  # still inside the restarted quiet

    group_clock.advance(2.0)
    await group.check_occupancy(now=True)
    assert newborn.state in ("quitting", "quitted")


async def test_new_pressure_during_the_quiet_restarts_it(make_group, group_clock):
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=60.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    newborn = group.worker_handler_map["standard_0002"]
    declare_cpu(group.reception, 5.0)
    declare_cpu(newborn, 1.0)
    await group.check_occupancy(now=True)  # reopen: quiet running

    group_clock.advance(50.0)
    declare_cpu(group.reception, 55.0)  # the CPU speaks again mid-quiet
    await group.check_occupancy(now=True)  # blocked (+ a third is grown)
    declare_cpu(group.reception, 5.0)
    await group.check_occupancy(now=True)  # reopened: restarted again

    group_clock.advance(59.0)
    for worker_handler in group.living_workers:
        declare_cpu(worker_handler, 1.0)
    await group.check_occupancy(now=True)

    assert all(w.state == "running" for w in group.living_workers)


async def test_a_worker_with_users_is_consolidated_after_the_quiet(
    make_group, commander, group_clock
):
    # No absolute "a worker with users cannot close": after the descent and
    # the quiet, the spare's user is redistributed — the consolidation stands.
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=60.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    newborn = group.worker_handler_map["standard_0002"]
    resident = await arrival(commander, group, "resident")
    assert resident == "standard_0002"

    declare_cpu(group.reception, 5.0)
    declare_cpu(newborn, 2.0)
    await group.check_occupancy(now=True)  # reopen
    group_clock.advance(61.0)
    await group.check_occupancy(now=True)  # quiet over: the spare is judged

    assert newborn.state in ("quitting", "quitted")


async def test_sticky_users_stand_until_the_intentional_retirement(
    make_group, commander, group_clock
):
    group = await grown_group(make_group, cpu_retirement_quiet_seconds=60.0)
    declare_cpu(group.reception, 55.0)
    await group.check_occupancy(now=True)
    newborn = group.worker_handler_map["standard_0002"]
    home = await arrival(commander, group, "settler")
    assert home == "standard_0002"

    declare_cpu(group.reception, 5.0)
    declare_cpu(newborn, 2.0)
    await group.check_occupancy(now=True)  # reopen: suspended
    group_clock.advance(30.0)
    await group.check_occupancy(now=True)  # still quiet: suspended

    assert group.user_worker_map["settler"] == "standard_0002"  # untouched so far
    assert newborn.state == "running"


def test_the_quiet_is_a_duration_and_zero_is_one(make_group):
    # The validation is the policy's, and it lists what is wrong: a negative
    # quiet is out of range, zero is a legitimate duration.
    with pytest.raises(GroupPolicyError, match="cpu_retirement_quiet_seconds"):
        make_group(cpu_retirement_quiet_seconds=-1.0)

    assert make_group(cpu_retirement_quiet_seconds=0.0).cpu_retirement_quiet_seconds == 0.0
    # And a group that names it nowhere runs on the dataclass default.
    assert make_group().cpu_retirement_quiet_seconds == 60.0
