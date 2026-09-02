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

"""A worker is born only for a user who is already there.

Contract tests. The periodic check births nothing while a worker lives; an
empty group gets its reception back; the saturation is written by the
placement that was refused, and lifted by the check once the group may grow.
"""

from __future__ import annotations

import pytest

from genro_asgi.spa.orchestration import AssignmentRefused
from genro_asgi.spa.orchestration.group_handler import GroupHandler
from genro_asgi.spa.orchestration.group_policy import GroupPolicy, GroupPolicyError

from .test_orchestration_cpu_growth import arrival, declare_cpu
from .test_orchestration_group_handler import commander  # noqa: F401
from .test_orchestration_group_handler import group_settings  # noqa: F401
from .test_orchestration_group_handler import instance_root  # noqa: F401
from .test_orchestration_group_handler import make_group  # noqa: F401


def test_the_reserve_setpoint_is_gone():
    assert "newcomer_reserve_count" not in GroupPolicy.SETPOINTS
    with pytest.raises(GroupPolicyError) as refusal:
        GroupPolicy.from_settings({"newcomer_reserve_count": 1})
    assert "newcomer_reserve_count: unknown setpoint" in refusal.value.violations


def test_the_reserve_judges_are_gone():
    assert not hasattr(GroupHandler, "_has_room")
    assert not hasattr(GroupHandler, "_placeable_newcomers")
    assert not hasattr(GroupHandler, "_grow")


async def test_the_periodic_check_births_nothing_while_a_worker_lives(make_group):
    # The old reserve forked here on a picture it read as full; the check must not.
    group = make_group()
    await group.start_worker()

    for _ in range(3):
        await group.check_occupancy(now=True)

    assert len(group.worker_handler_map) == 1


async def test_a_cpu_closed_only_worker_is_not_doubled_by_the_check(make_group):
    group = make_group(cpu_admission_close_percent=50.0)
    await group.start_worker()
    declare_cpu(group.reception, 90.0)

    for _ in range(3):
        await group.check_occupancy(now=True)

    assert group.reception.cpu_admission_open is False
    assert len(group.worker_handler_map) == 1


async def test_an_empty_group_gets_its_reception_back_at_the_check(make_group):
    group = make_group()
    await group.start_worker()
    group.reception.state = "quitted"

    await group.check_occupancy(now=True)

    assert group.reception is not None
    assert group.reception.state == "running"
    assert len(group.worker_handler_map) == 2


async def test_a_refused_placement_saturates_and_the_check_lifts_it(make_group, commander):
    group = make_group(cpu_admission_close_percent=50.0, worker_max_users=1)
    await group.start_worker()
    await arrival(commander, group, "first")
    declare_cpu(group.reception, 90.0)
    group._judge_cpu_admission()
    assert group.reception.cpu_admission_open is False

    commander.state = "quitting"  # the memory veto: no birth while not running
    with pytest.raises(AssignmentRefused):
        await arrival(commander, group, "second")
    assert group.state == "saturated"
    assert len(group.worker_handler_map) == 1

    commander.state = "running"
    await group.check_occupancy(now=True)
    assert group.state == "running"
    assert len(group.worker_handler_map) == 1
