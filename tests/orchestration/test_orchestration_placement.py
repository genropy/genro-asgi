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

"""Where a user lands: the walk down from the fullest, and the four refusals.

The subject here is the JUDGEMENT, not the processes: the workers are real
``WorkerHandler`` over a real group and a real vertex, but none of them has a
process under it — what a placement reads is the ``state`` and the last photo,
and both are written straight in, the way the machine writes them. The processes
have their own tests, one file over.

The occupancy of this group is measured against a round million of bytes — the
whole concession is the group's quota and the whole quota is what one worker may
hold — so a photo of 780_000 bytes is a worker standing at 78% and the arithmetic
of every refusal is readable in the numbers themselves.
"""

from __future__ import annotations

import pytest

from genro_asgi.spa.orchestration import (
    AssignmentRefused,
    GroupHandler,
    NoRoomError,
    SpaCommander,
    WorkerHandler,
    WorkerQuittingError,
    WorkerRestartingError,
)

#: What one worker of these groups reads as full.
MEMORY_CEILING = 1_000_000


@pytest.fixture
def commander(tmp_path):
    return SpaCommander(tmp_path / "frozen_users")


@pytest.fixture
def group(commander, tmp_path):
    """A group nobody has launched anything in: its policies are the defaults."""
    return GroupHandler(
        commander,
        "standard",
        memory_concession_bytes=MEMORY_CEILING,
        instance_dir=tmp_path / "i",
        frozen_users_path=tmp_path / "frozen_users",
        entry_module="never.launched",
    )


def worker_at(group, name: str, occupancy_percent: float, state: str = "running"):
    """One real worker of the group, standing at that occupancy, with no process under it."""
    worker_handler = WorkerHandler(group, name, **group.worker_settings)
    worker_handler.state = state
    worker_handler.worker_snapshot = {
        "rss_bytes": int(MEMORY_CEILING * occupancy_percent / 100)
    }
    group.worker_handler_map[name] = worker_handler
    return worker_handler


def newcomer(commander, cid: str = "cid-a") -> str:
    """A user the vertex has minted and nobody has ever measured."""
    return commander.resolve_user(cid)


async def test_a_photo_reads_as_the_percentage_it_is_and_never_over_full(group):
    assert group.get_occupancy_percent(None) == 0.0
    assert group.get_occupancy_percent({}) == 0.0
    assert group.get_occupancy_percent({"rss_bytes": MEMORY_CEILING // 4}) == 25.0
    assert group.get_occupancy_percent({"rss_bytes": 3 * MEMORY_CEILING}) == 100.0


async def test_a_worker_reads_as_full_at_its_own_share_of_the_group_quota(commander, tmp_path):
    group = GroupHandler(
        commander,
        "standard",
        memory_concession_bytes=MEMORY_CEILING,
        memory_max_percent=50.0,
        worker_memory_max_percent=50.0,
        instance_dir=tmp_path / "i",
        frozen_users_path=tmp_path / "f",
        entry_module="never.launched",
    )

    # The cascade: half the concession is this group's quota, half of that quota
    # is what one of its workers may hold — so a quarter of the machine is a
    # worker of this group standing at its full.
    assert group.memory_quota_bytes == MEMORY_CEILING / 2
    assert group.get_occupancy_percent({"rss_bytes": MEMORY_CEILING // 4}) == 100.0
    assert group.get_occupancy_percent({"rss_bytes": MEMORY_CEILING // 8}) == 50.0


async def test_a_group_that_measures_nothing_reads_every_worker_as_empty(commander, tmp_path):
    group = GroupHandler(
        commander, "standard", instance_dir=tmp_path / "i",
        frozen_users_path=tmp_path / "f", entry_module="never.launched",
    )

    assert group.get_occupancy_percent({"rss_bytes": 10**9}) == 0.0
    assert group.memory_quota_bytes is None
    assert group.memory_occupied_percent == 0.0


async def test_the_fullest_worker_that_still_takes_him_is_the_one_that_gets_him(group, commander):
    worker_at(group, "standard_0001", 10.0)
    worker_at(group, "standard_0002", 20.0)
    worker_at(group, "standard_0003", 60.0)
    user = newcomer(commander)

    assert group.assign_user(user) == "standard_0003"
    assert group.user_worker_map == {user: "standard_0003"}


async def test_the_walk_goes_past_the_one_with_no_room_and_stops_at_the_next(group, commander):
    worker_at(group, "standard_0001", 10.0)
    worker_at(group, "standard_0002", 50.0)
    # 78 + the 5 percent a user nobody measured is expected to cost is over the
    # setpoint of 80: he does not fit, and the class of the refusal says so.
    worker_at(group, "standard_0003", 78.0)
    user = newcomer(commander)

    assert group.assign_user(user) == "standard_0002"


async def test_what_he_cost_where_he_was_is_what_he_is_expected_to_cost_here(group, commander):
    worker_at(group, "standard_0001", 10.0)
    worker_at(group, "standard_0002", 50.0)
    worker_at(group, "standard_0003", 70.0)
    user = newcomer(commander)
    commander.user_map[user]["occupancy_percent"] = 25.0

    # 70 + 25 is over the setpoint, 50 + 25 is exactly at it.
    assert group.assign_user(user) == "standard_0002"


async def test_the_reception_keeps_its_reserve_and_takes_less_than_the_others(group, commander):
    reception = worker_at(group, "standard_0001", 28.0)
    worker_at(group, "standard_0002", 28.0)
    user = newcomer(commander)

    # Both stand at 28, but the reception's own setpoint is the difference
    # between the group's and its reserve: 80 - 50 = 30, and 28 + 5 is over it.
    assert group.get_worker_cap(reception) == 30.0
    assert group.assign_user(user) == "standard_0002"


async def test_two_placements_in_a_row_are_judged_on_the_same_photo(group, commander):
    worker_at(group, "standard_0001", 0.0)
    worker_at(group, "standard_0002", 70.0)
    first = newcomer(commander, "cid-a")
    second = newcomer(commander, "cid-b")

    # 70 + 5 fits, and it still reads 70 when the second one is judged: the
    # overshoot of one newcomer is the declared price of not locking a photo.
    assert group.assign_user(first) == "standard_0002"
    assert group.assign_user(second) == "standard_0002"


async def test_a_worker_with_no_room_refuses_with_the_class_that_says_so(group):
    worker_handler = worker_at(group, "standard_0002", 78.0)
    worker_at(group, "standard_0001", 0.0)

    with pytest.raises(NoRoomError, match="would stand at 83.0%"):
        worker_handler.assign_user("mario", 5.0)


async def test_a_restarting_worker_refuses_with_the_class_that_says_it_comes_back(group):
    worker_handler = worker_at(group, "standard_0001", 0.0, state="restarting")

    with pytest.raises(WorkerRestartingError):
        worker_handler.assign_user("mario", 5.0)


async def test_a_worker_on_its_way_out_refuses_with_the_class_that_says_it_will_not(group):
    for state in ("quitting", "quitted", "aborted"):
        worker_handler = worker_at(group, f"standard_{state}", 0.0, state=state)

        with pytest.raises(WorkerQuittingError):
            worker_handler.assign_user("mario", 5.0)


async def test_a_worker_that_has_not_presented_itself_yet_takes_nobody(group):
    worker_handler = worker_at(group, "standard_0001", 0.0, state="starting")

    with pytest.raises(AssignmentRefused) as refusal:
        worker_handler.assign_user("mario", 5.0)

    assert type(refusal.value) is AssignmentRefused


async def test_a_worker_whose_process_has_ended_is_nobodys_candidate(group, commander):
    worker_at(group, "standard_0001", 0.0, state="quitted")
    user = newcomer(commander)

    with pytest.raises(AssignmentRefused):
        group.assign_user(user)

    assert group.living_workers == []
    assert group.reception is None


async def test_when_nobody_admits_the_wake_rings_and_the_base_rises(group, commander):
    worker_at(group, "standard_0001", 79.0)
    worker_at(group, "standard_0002", 79.0)
    user = newcomer(commander)
    assert group.ping_now_event.is_set() is False

    with pytest.raises(AssignmentRefused) as refusal:
        group.assign_user(user)

    assert type(refusal.value) is AssignmentRefused
    assert refusal.value.user == user
    assert group.ping_now_event.is_set() is True
    assert group.user_worker_map == {}
