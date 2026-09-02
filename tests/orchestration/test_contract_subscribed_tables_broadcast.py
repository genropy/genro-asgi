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

"""The source filter is pushed: every worker learns the set, whoever moved it.

A worker filters the commits of its own site against ``subscribed_tables``. That
set is global — it belongs to the desk — and no reply carries it any more: the
commander pushes it to EVERY living worker on every transition of it (a table
gaining its first subscriber, or losing its last), and to a newborn worker at
its first presentation. A worker that subscribed nothing itself therefore filters
with the same set as the one that did.
"""

from __future__ import annotations

import pytest

from genro_asgi.spa.orchestration import FreezeHandler

from .conftest import XT_DeskLane, wait_for

TABLE = "customer"


@pytest.fixture
async def two_lanes(desk_lane, second_desk_lane):
    """The two lanes with one page each, on the same commander and group."""
    desk_lane.worker.add_connection("c1", sticky_cid="spa-c1")
    desk_lane.worker.add_page("p1", "c1")
    second_desk_lane.worker.add_connection("c2", sticky_cid="spa-c2")
    second_desk_lane.worker.add_page("p2", "c2")
    return desk_lane, second_desk_lane


async def subscribe(lane, page_id, table, subscribe=True):
    """Place the subscription the way the site places it, off the loop."""
    return await lane.verb(
        "subscribeTable", "alice", table=table, page_id=page_id, subscribe=subscribe
    )


async def test_a_subscription_on_one_worker_reaches_the_other(two_lanes):
    # wf:contract: a page subscribing a table on lane 1 leaves lane 2 — which
    # wf:contract: placed no call at all — with the same source filter, and a
    # wf:contract: commit on lane 2 then reaches the subscriber on lane 1.
    lane, other = two_lanes
    await subscribe(lane, "p1", TABLE)

    await wait_for(lambda: other.worker.subscribed_tables == {TABLE})

    await other.open_request()
    await other.verb("notifyDbEvents", "alice", dbevents={TABLE: ["ins:1"]}, page_id="p2")
    await other.verb("collect_page", "p2")

    await lane.open_request()
    delivery = await lane.verb("collect_page", "p1")
    assert [deposit["table"] for deposit in delivery["dbevents"]] == [TABLE]
    assert delivery["dbevents"][0]["from_page_id"] == "p2"


async def test_a_second_subscriber_of_the_same_table_pushes_nothing(two_lanes, monkeypatch):
    # wf:contract: only a TRANSITION of the global set is announced: a table
    # wf:contract: that already has a subscriber gains another one in silence.
    lane, other = two_lanes
    await subscribe(lane, "p1", TABLE)
    await wait_for(lambda: other.worker.subscribed_tables == {TABLE})

    pushes = []
    for handler in (lane.worker_handler, other.worker_handler):
        monkeypatch.setattr(
            handler, "push_subscribed_tables", lambda name=handler.name: pushes.append(name)
        )

    await subscribe(other, "p2", TABLE)

    assert pushes == []
    assert lane.desk.subscribed_tables == [TABLE]


async def test_the_last_subscriber_leaving_empties_every_worker(two_lanes):
    # wf:contract: the unsubscribe of the last subscriber is a transition too:
    # wf:contract: both workers lose the table from their source filter.
    lane, other = two_lanes
    await subscribe(lane, "p1", TABLE)
    await wait_for(lambda: other.worker.subscribed_tables == {TABLE})

    await subscribe(lane, "p1", TABLE, subscribe=False)

    await wait_for(lambda: lane.worker.subscribed_tables == set())
    await wait_for(lambda: other.worker.subscribed_tables == set())


async def test_dropping_the_only_subscribing_page_empties_every_worker(two_lanes):
    # wf:contract: a page dropped at the desk takes its subscriptions with it,
    # wf:contract: and the set that loses its last subscriber is announced.
    lane, other = two_lanes
    await subscribe(lane, "p1", TABLE)
    await wait_for(lambda: other.worker.subscribed_tables == {TABLE})

    lane.desk.drop_page("p1")

    await wait_for(lambda: lane.worker.subscribed_tables == set())
    await wait_for(lambda: other.worker.subscribed_tables == set())


async def test_the_replayed_subscriptions_of_a_woken_page_are_announced(two_lanes):
    # wf:contract: the wake replays a row's subscriptions through
    # wf:contract: install_page_subscriptions, and the workers learn the tables
    # wf:contract: it brings back — one announcement even for several tables.
    lane, other = two_lanes

    lane.desk.install_page_subscriptions("p9", ["orders"])

    await wait_for(lambda: lane.worker.subscribed_tables == {"orders"})
    await wait_for(lambda: other.worker.subscribed_tables == {"orders"})


async def test_a_newborn_worker_gets_the_set_at_its_first_presentation(desk_lane, tmp_path):
    # wf:contract: a worker born after the subscription placed no call and saw
    # wf:contract: no transition: its first presentation is what fetches it the
    # wf:contract: whole set.
    desk_lane.worker.add_connection("c1", sticky_cid="spa-c1")
    desk_lane.worker.add_page("p1", "c1")
    await subscribe(desk_lane, "p1", TABLE)
    await wait_for(lambda: desk_lane.desk.subscribed_tables == [TABLE])

    newborn = XT_DeskLane(
        desk_lane.commander,
        desk_lane.worker_handler.group_handler,
        FreezeHandler(tmp_path / "frozen_users_w3"),
        worker_name="w3",
    )
    await newborn.open()
    try:
        await wait_for(lambda: newborn.worker.subscribed_tables == {TABLE})
    finally:
        await newborn.close()
