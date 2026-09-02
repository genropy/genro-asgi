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

"""Phase 4 contract: table events — own ops, own species, one index.

Derived from ``tests/test_spa_dbevents.py``. The ops keep the pre_refactoring
signatures (``subscribeTable`` :1483, ``notifyDbEvents`` :1524) and those DO NOT
move.

**Amended by Phase 9** (foreman decision, notes.md): the mechanism these tests
photographed — the worker's own ``SubscriptionIndex``, the local fan-out, the
``dbevents`` mailbox on the page row — is dead. The index lives at the
commander's desk, ``subscribeTable`` files the interest there with a synchronous
lane call, the deposits accumulate on the request slot and travel to the desk at
the end of the request, and a page reads them back through its own exchange. So
the subscription tests watch the desk's index and the delivery tests watch the
collect.
"""

from __future__ import annotations

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker

from .conftest import wait_for

WORKER_NAME = "standard_0001"


@pytest.fixture
def worker(tmp_path):
    deposit = FreezeHandler(tmp_path / "frozen_users")
    made = SpaWorker(WORKER_NAME, freeze_handler=deposit, deposit_lock_retry_interval=0.01)
    made.new_page("alice", page_id="p0", connection_id="s1")
    made.new_page("alice", page_id="p1", connection_id="s1")
    return made


@pytest.fixture
async def lane(desk_lane):
    """The live lane with alice's two pages already on the worker."""
    desk_lane.worker.new_page("alice", page_id="p0", connection_id="s1")
    desk_lane.worker.new_page("alice", page_id="p1", connection_id="s1")
    return desk_lane


async def deposits_of(lane, page_id):
    """What one page reads when it exchanges: its deposits, retired from the desk."""
    return (await lane.verb("collect_page", page_id))["dbevents"]


# ----------------------------------------------------------------------
# The subscription: the row here, the index at the desk
# ----------------------------------------------------------------------


async def test_a_subscription_lands_on_the_index_and_on_the_row(lane):
    result = await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1")
    await lane.wait_filter_synced()

    assert result == {"page_id": "p1", "table": "glbl.user", "subscribe": True}
    assert lane.desk.page_subscriptions.pages_for("glbl.user") == {"p1"}
    assert lane.worker.page_register.get("p1")["table_subscriptions"] == {"glbl.user"}
    # The reply carries no table list: the source filter arrives on the CALL the
    # commander pushes, within the flight of that call.
    await wait_for(lambda: lane.worker.subscribed_tables == {"glbl.user"})


def test_a_subscription_for_an_unknown_page_is_an_error(worker):
    with pytest.raises(KeyError, match="ghost"):
        worker.subscribeTable("alice", table="glbl.user", page_id="ghost")


async def test_subscribe_mode_is_accepted_and_ignored(lane):
    """The vestigial parameter still travels from the callers: it must not refuse."""
    result = await lane.verb(
        "subscribeTable", "alice", table="glbl.user", page_id="p1", subscribeMode="fired"
    )

    assert result == {"page_id": "p1", "table": "glbl.user", "subscribe": True}
    assert lane.desk.page_subscriptions.pages_for("glbl.user") == {"p1"}


async def test_an_unsubscribe_clears_the_row_and_the_index(lane):
    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1")
    await lane.wait_filter_synced()

    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1", subscribe=False)
    await lane.wait_filter_synced()

    assert lane.worker.page_register.get("p1")["table_subscriptions"] == set()
    assert lane.desk.page_subscriptions.pages_for("glbl.user") == set()


async def test_a_dropped_page_leaves_no_subscription_behind(lane):
    """The worker forgets the row; the desk forgets the page when the fold reaches it."""
    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1")
    await lane.wait_filter_synced()

    await lane.verb("drop_page", "alice", "p1")
    lane.desk.drop_page("p1")

    assert lane.desk.page_subscriptions.pages_for("glbl.user") == set()
    assert "p1" not in lane.worker.page_register


# ----------------------------------------------------------------------
# notifyDbEvents: shaped once, filtered at the source, delivered by the desk
# ----------------------------------------------------------------------


async def test_a_commit_reaches_the_local_subscribers(lane):
    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1")
    await lane.wait_filter_synced()

    result = await lane.verb(
        "notifyDbEvents", "alice", dbevents={"glbl.user": ["ins:1"]}, reason="commit",
        page_id="p0",
    )

    assert result == {"tables": ["glbl.user"]}
    deposits = await deposits_of(lane, "p1")
    assert [(d["table"], d["batch"], d["from_page_id"], d["reason"]) for d in deposits] == [
        ("glbl.user", ["ins:1"], "p0", "commit")
    ]
    assert "ts" in deposits[0]


async def test_two_subscribing_pages_read_the_same_shaped_deposit(lane):
    lane.worker.new_page("alice", page_id="p2", connection_id="s1")
    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1")
    await lane.wait_filter_synced()
    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p2")
    await lane.wait_filter_synced()

    await lane.verb("notifyDbEvents", "alice", dbevents={"glbl.user": ["ins:1"]}, page_id="p0")

    first = await deposits_of(lane, "p1")
    second = await deposits_of(lane, "p2")
    assert first == second
    assert first[0]["ts"] == second[0]["ts"]


async def test_a_commit_nobody_subscribed_deposits_nothing(lane):
    """Filtered at the source: a table outside the cache never even reaches the wire."""
    result = await lane.verb(
        "notifyDbEvents", "alice", dbevents={"glbl.user": ["ins:1"]}, page_id="p1"
    )

    assert result == {"tables": []}
    assert await deposits_of(lane, "p0") == []
    assert await deposits_of(lane, "p1") == []


async def test_an_empty_batch_is_not_announced_at_all(lane):
    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1")
    await lane.wait_filter_synced()

    result = await lane.verb("notifyDbEvents", "alice", dbevents={"glbl.user": []}, page_id="p1")

    assert result == {"tables": []}
    assert await deposits_of(lane, "p1") == []


async def test_local_only_deposits_on_the_origin_page_alone(lane):
    """The hidden transaction: its events belong to the page that made them."""
    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1")
    await lane.wait_filter_synced()

    result = await lane.verb(
        "notifyDbEvents", "alice", dbevents={"glbl.user": ["ins:1"]}, page_id="p0",
        local_only=True,
    )

    assert result == {"tables": ["glbl.user"]}
    assert [d["batch"] for d in await deposits_of(lane, "p0")] == [["ins:1"]]
    assert await deposits_of(lane, "p1") == []


# ----------------------------------------------------------------------
# The species never mix
# ----------------------------------------------------------------------


async def test_the_deposit_drains_on_its_own_key_and_never_as_a_datachange(lane):
    await lane.verb("subscribeTable", "alice", table="glbl.user", page_id="p1")
    await lane.wait_filter_synced()
    await lane.verb(
        "setStoreSubscription", "alice", page_id="p1", storename="page", prefix="form"
    )
    await lane.verb("notifyDbEvents", "alice", dbevents={"glbl.user": ["ins:1"]}, page_id="p0")
    lane.worker.page_register.get("p1")["store"]["form.name"] = "Ada"

    collected = await lane.verb("collect_page", "p1")

    assert [d["table"] for d in collected["dbevents"]] == ["glbl.user"]
    assert [c["key"]["path"] for c in collected["datachanges"]] == ["form", "form.name"]
    assert (await lane.verb("collect_page", "p1"))["dbevents"] == []
