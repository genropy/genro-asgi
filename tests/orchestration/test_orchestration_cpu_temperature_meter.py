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

"""The commander-side CPU thermometer: cheap, observation-only process readings.

Implementation tests.  The meter reads the process's cumulative CPU clock
through psutil; two readings make one temperature.  It never asks the worker for a photo and
none of its fields is consumed by orchestration.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from genro_asgi.spa.orchestration import worker_handler as worker_handler_module
from genro_asgi.spa.orchestration import spa_commander as spa_commander_module
from genro_asgi.spa.orchestration.worker_handler import WorkerHandler

from .test_orchestration_group_handler import commander  # noqa: F401
from .test_orchestration_group_handler import group_settings  # noqa: F401
from .test_orchestration_group_handler import instance_root  # noqa: F401
from .test_orchestration_group_handler import make_group  # noqa: F401


class ProcessDouble:
    """A live process identity for a handler whose CPU clock is under test."""

    def __init__(self, pid: int) -> None:
        self.pid = pid


def handler_double() -> WorkerHandler:
    """One handler without a wire: only its process clock belongs to this story."""
    group = SimpleNamespace()
    group.envelope_handler = lambda envelope: envelope
    group.cpu_grow_percent = None
    handler = WorkerHandler(
        group,
        "standard_0001",
        instance_dir="/tmp",
        frozen_users_path="/tmp",
        entry_module="unused",
    )
    handler.process = ProcessDouble(1234)
    handler.state = "running"
    handler.worker_snapshot = {"cpu_percent": 7.0}
    return handler


def test_two_readings_make_separate_temperature_telemetry():
    handler = handler_double()

    assert handler.record_cpu_reading((900, 1.0), sampled_at=10.0) is None
    assert handler.record_cpu_reading((900, 1.08), sampled_at=10.1) == pytest.approx(80.0)
    assert handler.cpu_temperature_percent == pytest.approx(80.0)
    assert handler.cpu_temperature_interval_seconds == pytest.approx(0.1)
    assert handler.cpu_temperature_sampled_at == pytest.approx(10.1)
    assert handler.worker_snapshot["cpu_percent"] == 7.0


def test_a_reused_pid_starts_a_new_measurement_instead_of_inventing_cpu():
    handler = handler_double()
    handler.record_cpu_reading((900, 4.0), sampled_at=10.0)
    handler.record_cpu_reading((900, 4.08), sampled_at=10.1)

    assert handler.record_cpu_reading((1200, 0.01), sampled_at=10.2) is None
    assert handler.cpu_temperature_percent is None


def test_a_full_photo_and_the_temperature_remain_independent():
    handler = handler_double()
    handler.cpu_temperature_percent = 72.0

    handler.envelope_handler.on_worker_snapshot({"cpu_percent": 11.0})

    assert handler.worker_snapshot["cpu_percent"] == 11.0
    assert handler.cpu_temperature_percent == 72.0


def test_fresh_temperature_closes_and_reopens_cpu_admission(
    commander, make_group, monkeypatch
):
    group = make_group(cpu_grow_percent=50.0, cpu_grow_rearm_percent=30.0)
    handler = handler_double()
    handler.process = None
    handler.group_handler = group
    group.worker_handler_map[handler.name] = handler
    readings = iter([(900, 1.0), (900, 1.08), (900, 1.081)])
    monkeypatch.setattr(handler, "get_process_cpu_reading", lambda: next(readings))
    started = worker_handler_module.time.monotonic()

    commander.sample_cpu_temperatures(sampled_at=started)
    commander.sample_cpu_temperatures(sampled_at=started + 0.1)
    assert handler.cpu_temperature_percent == pytest.approx(80.0)
    assert handler.cpu_admission_open is False
    assert handler.worker_snapshot["cpu_percent"] == 7.0

    handler.worker_snapshot["cpu_percent"] = 99.0
    commander.sample_cpu_temperatures(sampled_at=started + 0.2)
    assert handler.cpu_admission_open is True


def test_temperature_is_observed_even_when_the_cpu_policy_is_off(
    commander, make_group, monkeypatch
):
    group = make_group(cpu_grow_percent=None)
    handler = handler_double()
    handler.process = None
    handler.group_handler = group
    group.worker_handler_map[handler.name] = handler
    called = 0

    def reading():
        nonlocal called
        called += 1
        return 900, 1.0

    monkeypatch.setattr(handler, "get_process_cpu_reading", reading)

    commander.sample_cpu_temperatures(sampled_at=10.0)

    assert called == 1


def test_an_unreadable_process_does_not_rejudge_a_stale_photo(
    commander, make_group, monkeypatch
):
    group = make_group(cpu_grow_percent=50.0, cpu_grow_rearm_percent=30.0)
    handler = handler_double()
    handler.process = None
    handler.group_handler = group
    handler.worker_snapshot["cpu_percent"] = 90.0
    group.worker_handler_map[handler.name] = handler
    monkeypatch.setattr(handler, "get_process_cpu_reading", lambda: None)

    commander.sample_cpu_temperatures(sampled_at=10.0)

    assert handler.cpu_admission_open is True


def test_a_stale_temperature_is_not_an_orchestration_input(
    commander, make_group, monkeypatch
):
    group = make_group(cpu_grow_percent=50.0, cpu_grow_rearm_percent=30.0)
    handler = handler_double()
    handler.process = None
    handler.group_handler = group
    handler.cpu_temperature_percent = 90.0
    handler.cpu_temperature_sampled_at = 10.0
    handler.cpu_temperature_interval_seconds = 0.1
    group.worker_handler_map[handler.name] = handler
    monkeypatch.setattr(worker_handler_module.time, "monotonic", lambda: 12.0)

    group._judge_cpu_admission()

    assert handler.cpu_admission_open is True


async def test_one_meter_clock_samples_every_group(commander, monkeypatch):
    samples: list[float] = []
    group = SimpleNamespace(
        name="measured",
        living_workers=[],
    )
    commander.group_map[group.name] = group
    commander.cpu_temperature_sample_seconds = 0.001
    monkeypatch.setattr(
        commander,
        "sample_cpu_temperatures",
        lambda *, sampled_at: samples.append(sampled_at),
    )
    task = asyncio.create_task(commander.cpu_meter_loop())
    try:
        while len(samples) < 3:
            await asyncio.sleep(0.001)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert samples == sorted(samples)


async def test_pool_census_exposes_temperature_without_putting_it_in_the_photo(
    commander, make_group, monkeypatch
):
    group = make_group()
    handler = handler_double()
    handler.process = None
    handler.group_handler = group
    handler.cpu_temperature_percent = 62.0
    handler.cpu_temperature_interval_seconds = 0.1
    handler.cpu_temperature_sampled_at = 10.0
    group.worker_handler_map[handler.name] = handler
    commander.group_map[group.name] = group

    async def worker_census(_handler):
        return {"name": handler.name}

    monkeypatch.setattr(commander, "_get_worker_census", worker_census)
    monkeypatch.setattr(spa_commander_module.time, "monotonic", lambda: 10.25)

    census = await commander.get_pool_census()

    group_row = census["groups"][group.name]["workers"][handler.name]
    assert group_row["cpu_temperature_percent"] == 62.0
    assert group_row["cpu_temperature_interval_seconds"] == 0.1
    assert group_row["cpu_temperature_age_seconds"] == 0.25
    assert handler.worker_snapshot == {"cpu_percent": 7.0}
