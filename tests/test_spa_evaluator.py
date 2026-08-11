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

"""Tests for OccupancyEvaluator: components, the ratio space, history and rates.

Windows are SEEDED through the commander's public ``record_occupancy`` (and
``count_forward`` for the rates), exactly as the occupancy probe feeds them — no
internal wiring. Each reading is a raw report of the fixed shape the worker
sends (``cpu``, ``rss``, ``executor{busy,total}``).
"""

from __future__ import annotations

import math
import time
from typing import Any

import pytest

from genro_asgi.spa.commander import UserStickyCommander
from genro_asgi.spa.evaluator import COMPONENT_NAMES, SMOOTHING_ROWS, OccupancyEvaluator


def make_commander(tmp_path: Any, **kwargs: Any) -> UserStickyCommander:
    """A commander with one enrolled worker and a hub that is never started."""
    running = UserStickyCommander(workers=0, path=str(tmp_path / "hub.sock"), **kwargs)
    running.worker_roster["w1"] = running.new_roster_row(0, None)
    running.worker_roster["w1"]["status"] = "active"
    return running


def report(
    cpu: float | None = None,
    rss: int | None = None,
    busy: int = 0,
    total: int = 0,
    reusable: int | None = None,
) -> dict[str, Any]:
    """A raw occupancy reading with only the fields the formula reads set."""
    return {
        "cpu": cpu,
        "rss": rss,
        "reusable": reusable,
        "executor": {"busy": busy, "total": total},
    }


# ----------------------------------------------------------------------
# A worker with no rows admits (both readings 0.0)
# ----------------------------------------------------------------------


def test_fresh_worker_reads_zero_occupancy(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    assert commander.evaluator.worker_saturation("ghost") == 0.0
    assert commander.evaluator.worker_load("ghost") == 0.0
    assert commander.evaluator.worker_components("ghost") == {}
    assert commander.evaluator.worker_history("ghost") == []


def test_enrolled_worker_with_an_empty_window_reads_zero(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    assert commander.evaluator.worker_saturation("w1") == 0.0
    assert commander.evaluator.worker_load("w1") == 0.0
    assert commander.evaluator.worker_history("w1") == []


# ----------------------------------------------------------------------
# The components: average each over the window
# ----------------------------------------------------------------------


def test_executor_component_is_busy_over_total(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    commander.record_occupancy("w1", report(busy=7, total=14))
    assert commander.evaluator.worker_components("w1") == {"executor": 0.5}
    # ratio space: 0.5 of the resource against the 0.8 target
    assert commander.evaluator.worker_saturation("w1") == pytest.approx(0.625)


def test_executor_component_is_clamped_when_busy_exceeds_total(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    # the pool counts queued calls as busy (demand, not slots held): with 10
    # calls in flight on 4 threads the raw ratio is 2.5 — the judgment is "full"
    commander.record_occupancy("w1", report(busy=10, total=4))
    assert commander.evaluator.worker_components("w1") == {"executor": 1.0}
    # the raw component saturates at 1.0; over the 0.8 target that reads 1.25
    assert commander.evaluator.worker_saturation("w1") == pytest.approx(1.25)


def test_cpu_component_is_clamped_to_one_core(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    commander.record_occupancy("w1", report(cpu=1.4))
    # a process can burn more than one core of wall over the interval on a busy
    # box; the GIL wall means one core saturates, so cpu clamps to 1.0
    assert commander.evaluator.worker_components("w1") == {"cpu": 1.0}


def test_occupancy_is_the_max_of_the_averaged_components(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=100)
    # cpu 0.2, executor 0.5, memory 50MB/100MB = 0.5 -> max = 0.5
    commander.record_occupancy("w1", report(cpu=0.2, rss=50 * 1024 * 1024, busy=5, total=10))
    components = commander.evaluator.worker_components("w1")
    assert components == {"cpu": 0.2, "executor": 0.5, "memory": 0.5}
    assert commander.evaluator.worker_saturation("w1") == pytest.approx(0.5 / 0.8)


def test_component_is_averaged_before_the_max_is_taken(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    # two rows of executor: 1.0 then 0.0 -> averaged 0.5 (the spike is absorbed)
    commander.record_occupancy("w1", report(busy=10, total=10))
    commander.record_occupancy("w1", report(busy=0, total=10))
    assert commander.evaluator.worker_components("w1")["executor"] == 0.5
    assert commander.evaluator.worker_saturation("w1") == pytest.approx(0.625)


def test_smoothing_averages_only_the_last_k_rows(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    # SMOOTHING_ROWS rows at executor 0.0, then two at 1.0: the average over the
    # last SMOOTHING_ROWS still includes some zeros, so it sits between 0 and 1
    for _ in range(SMOOTHING_ROWS):
        commander.record_occupancy("w1", report(busy=0, total=10))
    commander.record_occupancy("w1", report(busy=10, total=10))
    commander.record_occupancy("w1", report(busy=10, total=10))
    assert commander.evaluator.worker_components("w1")["executor"] == 2.0 / SMOOTHING_ROWS


# ----------------------------------------------------------------------
# The memory component depends on a configured limit AND an rss reading
# ----------------------------------------------------------------------


def test_memory_component_absent_without_a_configured_limit(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)  # no memory_limit_mb
    commander.record_occupancy("w1", report(rss=50 * 1024 * 1024, busy=1, total=10))
    components = commander.evaluator.worker_components("w1")
    assert "memory" not in components
    assert set(components) == {"executor"}


def test_memory_component_absent_when_rss_is_none(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=100)  # limit set, no rss
    commander.record_occupancy("w1", report(rss=None, cpu=0.3))
    components = commander.evaluator.worker_components("w1")
    assert "memory" not in components
    assert components == {"cpu": 0.3}


def test_memory_component_is_clamped_at_the_limit(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=100)
    # rss beyond the limit is the normal pre-restart state: the judgment
    # saturates at "full", the raw rss stays in the archived report
    commander.record_occupancy("w1", report(rss=200 * 1024 * 1024))
    assert commander.evaluator.worker_components("w1") == {"memory": 1.0}
    assert commander.evaluator.worker_saturation("w1") == pytest.approx(1.25)


def test_memory_component_present_with_limit_and_rss(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=200)
    commander.record_occupancy("w1", report(rss=100 * 1024 * 1024))
    assert commander.evaluator.worker_components("w1") == {"memory": 0.5}


def test_reusable_lowers_the_memory_component(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=200)
    # 100MB resident of which 50MB is free heap: the live memory is 50MB
    commander.record_occupancy(
        "w1", report(rss=100 * 1024 * 1024, reusable=50 * 1024 * 1024)
    )
    assert commander.evaluator.worker_components("w1") == {"memory": 0.25}


def test_memory_degrades_to_the_rss_ratio_without_reusable(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=200)
    # None (no glibc) and the field missing altogether both count as 0
    commander.record_occupancy("w1", report(rss=100 * 1024 * 1024, reusable=None))
    assert commander.evaluator.worker_components("w1") == {"memory": 0.5}
    assert commander.evaluator.row_components({"rss": 100 * 1024 * 1024}) == {
        "memory": 0.5
    }


def test_memory_component_floors_at_zero_when_reusable_exceeds_rss(
    tmp_path: Any,
) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=200)
    # the trim madvises free chunks away while they still count as reusable:
    # the subtraction goes negative and the clamp floors it
    commander.record_occupancy(
        "w1", report(rss=50 * 1024 * 1024, reusable=80 * 1024 * 1024)
    )
    assert commander.evaluator.worker_components("w1") == {"memory": 0.0}


def test_memory_component_saturates_on_live_memory_past_the_limit(
    tmp_path: Any,
) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=100)
    # 300MB resident, 50MB reusable -> 250MB live, still beyond the limit
    commander.record_occupancy(
        "w1", report(rss=300 * 1024 * 1024, reusable=50 * 1024 * 1024)
    )
    assert commander.evaluator.worker_components("w1") == {"memory": 1.0}


def test_component_averaged_only_over_rows_that_carry_it(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    # cpu present in one row only; its average uses that single contributing row
    commander.record_occupancy("w1", report(cpu=None, busy=2, total=10))
    commander.record_occupancy("w1", report(cpu=0.8, busy=2, total=10))
    components = commander.evaluator.worker_components("w1")
    assert components["cpu"] == 0.8
    assert components["executor"] == 0.2


# ----------------------------------------------------------------------
# The ratio space: targets, the GATE reading and the QUANTITY reading
# ----------------------------------------------------------------------


def test_targets_default_to_the_uniform_admission_threshold(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    assert commander.evaluator.targets == dict.fromkeys(COMPONENT_NAMES, 0.8)


def test_component_targets_override_the_uniform_threshold(tmp_path: Any) -> None:
    commander = make_commander(
        tmp_path, admission_threshold=0.9, component_targets={"memory": 0.5}
    )
    assert commander.evaluator.targets == {"memory": 0.5, "cpu": 0.9, "executor": 0.9}


def test_ratios_divide_each_component_by_its_own_target(tmp_path: Any) -> None:
    commander = make_commander(
        tmp_path, memory_limit_mb=100, component_targets={"memory": 0.5}
    )
    # memory 0.4 against its own 0.5 target -> 0.8; executor 0.4 against 0.8 -> 0.5
    commander.record_occupancy("w1", report(rss=40 * 1024 * 1024, busy=4, total=10))
    ratios = commander.evaluator.ratios_of("w1")
    assert ratios["memory"] == pytest.approx(0.8)
    assert ratios["executor"] == pytest.approx(0.5)


def test_saturation_gates_high_where_load_stays_low(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=100)
    # one-hot: memory at its target, cpu and executor idle. The GATE reads the
    # bottleneck (1.0 — the worker is full), the QUANTITY reads the whole
    # picture and stays well under it: this is the distinction the policies buy.
    commander.record_occupancy(
        "w1", report(cpu=0.0, rss=80 * 1024 * 1024, busy=0, total=10)
    )
    assert commander.evaluator.worker_saturation("w1") == pytest.approx(1.0)
    assert commander.evaluator.worker_load("w1") == pytest.approx(1.0 / math.sqrt(3))
    assert commander.evaluator.worker_load("w1") < commander.evaluator.worker_saturation("w1")


def test_load_is_the_quadratic_mean_of_the_ratios(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, admission_threshold=1.0)
    # cpu 0.6, executor 0.8 against a 1.0 target -> quadratic mean of 0.6 and 0.8
    commander.record_occupancy("w1", report(cpu=0.6, busy=8, total=10))
    expected = math.sqrt((0.6**2 + 0.8**2) / 2)
    assert commander.evaluator.worker_load("w1") == pytest.approx(expected)
    assert commander.evaluator.worker_saturation("w1") == pytest.approx(0.8)


def test_ratios_empty_for_a_worker_with_no_measurable_component(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    commander.record_occupancy("w1", report(busy=0, total=0))
    assert commander.evaluator.ratios_of("w1") == {}
    assert commander.evaluator.worker_saturation("w1") == 0.0
    assert commander.evaluator.worker_load("w1") == 0.0


# ----------------------------------------------------------------------
# Target validation, at the commander constructor
# ----------------------------------------------------------------------


def test_unknown_component_target_is_rejected(tmp_path: Any) -> None:
    with pytest.raises(ValueError, match="unknown component target"):
        make_commander(tmp_path, component_targets={"disk": 0.5})


@pytest.mark.parametrize("value", [0.0, -0.1, 1.5])
def test_component_target_outside_the_unit_interval_is_rejected(
    tmp_path: Any, value: float
) -> None:
    with pytest.raises(ValueError, match="target must be in"):
        make_commander(tmp_path, component_targets={"cpu": value})


@pytest.mark.parametrize("value", [0.0, -0.1, 1.5])
def test_admission_threshold_outside_the_unit_interval_is_rejected(
    tmp_path: Any, value: float
) -> None:
    with pytest.raises(ValueError, match="admission_threshold target must be in"):
        make_commander(tmp_path, admission_threshold=value)


# ----------------------------------------------------------------------
# worker_history: one value per WHOLE-window row, the row's own max RATIO
# ----------------------------------------------------------------------


def test_history_is_the_per_row_saturation_over_the_whole_window(tmp_path: Any) -> None:
    commander = make_commander(tmp_path, memory_limit_mb=100)
    commander.record_occupancy("w1", report(cpu=0.1, busy=3, total=10))  # max 0.3 / 0.8
    commander.record_occupancy("w1", report(rss=80 * 1024 * 1024, busy=1, total=10))  # 0.8 / 0.8
    commander.record_occupancy("w1", report(busy=0, total=0))  # nothing measurable
    # The histogram shares the bar's axis: 1.0 is the admission target, and the
    # second row sits exactly on it.
    assert commander.evaluator.worker_history("w1") == [pytest.approx(0.375), 1.0, 0.0]


# ----------------------------------------------------------------------
# rates_of: rps and latency from the forward-counter deltas
# ----------------------------------------------------------------------


def test_rates_none_with_fewer_than_two_rows(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    commander.record_occupancy("w1", report(busy=1, total=10))
    assert commander.evaluator.rates_of("w1") == {"rps": None, "latency_ms": None}


def test_rates_none_for_an_unknown_worker(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    assert commander.evaluator.rates_of("ghost") == {"rps": None, "latency_ms": None}


def test_rates_from_the_counter_deltas_between_first_and_last_row(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    # first row: 0 forwards; then 10 forwards totalling 2.0s; second row snapshots
    commander.record_occupancy("w1", report(busy=0, total=10))
    for _ in range(10):
        commander.count_forward("w1", 0.2)
    # nudge the second row's ts so the elapsed wall is measurable and positive
    time.sleep(0.01)
    commander.record_occupancy("w1", report(busy=0, total=10))
    rates = commander.evaluator.rates_of("w1")
    assert rates["rps"] is not None and rates["rps"] > 0
    # mean forward time: 2.0s over 10 requests = 200ms
    assert rates["latency_ms"] is not None
    assert abs(rates["latency_ms"] - 200.0) < 1e-6


def test_rates_latency_none_when_no_request_completed(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    commander.record_occupancy("w1", report(busy=0, total=10))
    time.sleep(0.01)
    commander.record_occupancy("w1", report(busy=0, total=10))
    # no forward between the two rows -> zero request delta -> latency None
    assert commander.evaluator.rates_of("w1")["latency_ms"] is None


# ----------------------------------------------------------------------
# The evaluator is owned by the commander with the semantic parent name
# ----------------------------------------------------------------------


def test_evaluator_is_owned_by_the_commander(tmp_path: Any) -> None:
    commander = make_commander(tmp_path)
    assert isinstance(commander.evaluator, OccupancyEvaluator)
    assert commander.evaluator.commander is commander


def test_memory_limit_defaults_to_absent(tmp_path: Any) -> None:
    assert make_commander(tmp_path).memory_limit_mb is None
    assert make_commander(tmp_path, memory_limit_mb=256).memory_limit_mb == 256
