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

"""The observation stream: register mutations pushed worker → commander → watcher."""

from __future__ import annotations

import asyncio

import pytest

from .conftest import wait_for


@pytest.fixture
def wired_lane(desk_lane):
    """The lane, with its handler hanging in the group map like a launched one."""
    group = desk_lane.commander.group_map["standard"]
    group.worker_handler_map[desk_lane.worker_handler.name] = desk_lane.worker_handler
    return desk_lane


async def test_nobody_watching_leaves_the_worker_silent(wired_lane):
    assert wired_lane.worker.observation_on is False
    assert wired_lane.commander.observation_watched is False

    await wired_lane.verb("add_connection", "a1b2")

    assert wired_lane.worker.observation_on is False


async def test_a_watcher_switches_the_worker_on_and_hears_a_birth(wired_lane):
    queue: asyncio.Queue = asyncio.Queue()
    await wired_lane.commander.subscribe_observation(queue)
    assert wired_lane.worker.observation_on is True

    await wired_lane.verb("add_connection", "a1b2")
    await wait_for(lambda: queue.qsize() >= 2)
    await asyncio.sleep(0)

    events = {event["kind"]: event for event in [queue.get_nowait() for _ in range(queue.qsize())]}
    assert set(events) == {"new_user", "new_connection"}
    assert events["new_connection"]["source"] == "standard_0001"
    assert events["new_connection"]["data"]["user"].startswith("guest_")


async def test_the_last_watcher_leaving_switches_the_worker_off(wired_lane):
    queue: asyncio.Queue = asyncio.Queue()
    other: asyncio.Queue = asyncio.Queue()
    await wired_lane.commander.subscribe_observation(queue)
    await wired_lane.commander.subscribe_observation(other)

    await wired_lane.commander.unsubscribe_observation(queue)
    assert wired_lane.worker.observation_on is True

    await wired_lane.commander.unsubscribe_observation(other)
    assert wired_lane.worker.observation_on is False
    assert wired_lane.commander.observation_watched is False


async def test_the_fold_at_the_vertex_is_published_too(wired_lane):
    queue: asyncio.Queue = asyncio.Queue()
    await wired_lane.commander.subscribe_observation(queue)

    wired_lane.worker_handler.read_envelope(
        {"worker_events": [{"op": "new_user", "worker": "standard_0001", "user": "u1"}]}
    )

    event = await queue.get()
    assert event["kind"] == "new_user"
    assert event["source"] == "commander"
