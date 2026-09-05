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

"""store_get: one value per read, a CALL on the lane, never a stale copy.

The read side of the global store. The store lives on the commander alone, so
a read pays its round trip — the owner's own call (2026-08-21): a sub-commander
topology guarantees no shared disk, and the lane works on any of them.
"""

from __future__ import annotations

import datetime


async def test_a_read_answers_the_masters_current_value(worker_commander_lane):
    await worker_commander_lane.verb("store_set", "alice", "gnr.a", value=1)

    assert await worker_commander_lane.verb("store_get", "alice", "gnr.a") == 1

    worker_commander_lane.commander.global_register.set_item("gnr.a", 2)
    assert await worker_commander_lane.verb("store_get", "alice", "gnr.a") == 2


async def test_a_path_the_store_does_not_hold_answers_none(worker_commander_lane):
    assert await worker_commander_lane.verb("store_get", "alice", "gnr.missing") is None


async def test_typed_values_travel_whole(worker_commander_lane):
    stamp = datetime.datetime(2026, 8, 21, 10, 0, tzinfo=datetime.timezone.utc)
    worker_commander_lane.commander.global_register.set_item("CACHE_TS.adm_htag", stamp)

    assert await worker_commander_lane.verb("store_get", "alice", "CACHE_TS.adm_htag") == stamp


async def test_a_subtree_comes_back_as_a_bag(worker_commander_lane):
    worker_commander_lane.commander.global_register.set_item("gnr.counters.a", 1)
    worker_commander_lane.commander.global_register.set_item("gnr.counters.b", 2)

    subtree = await worker_commander_lane.verb("store_get", "alice", "gnr.counters")

    assert subtree["a"] == 1
    assert subtree["b"] == 2
