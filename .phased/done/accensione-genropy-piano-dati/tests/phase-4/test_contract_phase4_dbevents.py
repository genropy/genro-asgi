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

"""Phase 4 contract: table events — own ops, own index, own species. Local form.

Derived from ``tests/test_spa_dbevents.py``, restricted to what one process can
answer: the pre-alpha runs one worker of fact, so «announce locally» is the
whole announcement. The cross-worker fan-out (the ascent, ``/dbevents_in``, the
commander's page_subscriptions) is second-pass matter — but the ops keep the
pre_refactoring signatures (``subscribeTable`` :1483, ``notifyDbEvents`` :1524),
so the delivery between workers will not have to reopen them.
"""

from __future__ import annotations

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker

WORKER_NAME = "standard_0001"


@pytest.fixture
def worker(tmp_path):
    deposit = FreezeHandler(tmp_path / "frozen_users")
    made = SpaWorker(WORKER_NAME, freeze_handler=deposit, deposit_lock_retry_interval=0.01)
    made.new_page("alice", page_id="p0", session_id="s1")
    made.new_page("alice", page_id="p1", session_id="s1")
    return made


def deposits_of(worker, page_id):
    return worker.page_register.get(page_id)["dbevents"]


# ----------------------------------------------------------------------
# The subscription: the row and the index move together
# ----------------------------------------------------------------------


def test_a_subscription_lands_on_the_index_and_on_the_row(worker):
    result = worker.subscribeTable("alice", table="glbl.user", page_id="p1")

    assert result == {"page_id": "p1", "table": "glbl.user", "subscribe": True}
    assert worker.subscriptions.pages_for("glbl.user") == {"p1"}
    assert worker.page_register.get("p1")["table_subscriptions"] == {"glbl.user"}


def test_a_subscription_for_an_unknown_page_is_an_error(worker):
    with pytest.raises(KeyError, match="ghost"):
        worker.subscribeTable("alice", table="glbl.user", page_id="ghost")


def test_subscribe_mode_is_accepted_and_ignored(worker):
    """The vestigial parameter still travels from the callers: it must not refuse."""
    result = worker.subscribeTable(
        "alice", table="glbl.user", page_id="p1", subscribeMode="fired"
    )

    assert result == {"page_id": "p1", "table": "glbl.user", "subscribe": True}
    assert worker.subscriptions.pages_for("glbl.user") == {"p1"}


def test_an_unsubscribe_clears_the_row_and_the_index(worker):
    worker.subscribeTable("alice", table="glbl.user", page_id="p1")

    worker.subscribeTable("alice", table="glbl.user", page_id="p1", subscribe=False)

    assert worker.page_register.get("p1")["table_subscriptions"] == set()
    assert worker.subscriptions.pages_for("glbl.user") == set()


def test_a_dropped_page_leaves_no_subscription_behind(worker):
    worker.subscribeTable("alice", table="glbl.user", page_id="p1")

    worker.drop_page("alice", "p1")

    assert worker.subscriptions.pages_for("glbl.user") == set()


# ----------------------------------------------------------------------
# notifyDbEvents: the local fan-out, shaped once
# ----------------------------------------------------------------------


def test_a_commit_reaches_the_local_subscribers(worker):
    worker.subscribeTable("alice", table="glbl.user", page_id="p1")

    result = worker.notifyDbEvents(
        "alice", dbevents={"glbl.user": ["ins:1"]}, reason="commit", page_id="p0"
    )

    assert result == {"tables": ["glbl.user"]}
    deposits = deposits_of(worker, "p1")
    assert [(d["table"], d["batch"], d["from_page_id"], d["reason"]) for d in deposits] == [
        ("glbl.user", ["ins:1"], "p0", "commit")
    ]
    assert "ts" in deposits[0]


def test_two_subscribing_pages_read_the_same_shaped_deposit(worker):
    worker.new_page("alice", page_id="p2", session_id="s1")
    worker.subscribeTable("alice", table="glbl.user", page_id="p1")
    worker.subscribeTable("alice", table="glbl.user", page_id="p2")

    worker.notifyDbEvents("alice", dbevents={"glbl.user": ["ins:1"]}, page_id="p0")

    assert deposits_of(worker, "p1") == deposits_of(worker, "p2")
    assert deposits_of(worker, "p1")[0]["ts"] == deposits_of(worker, "p2")[0]["ts"]


def test_a_commit_nobody_subscribed_deposits_nothing(worker):
    result = worker.notifyDbEvents("alice", dbevents={"glbl.user": ["ins:1"]}, page_id="p1")

    assert result == {"tables": ["glbl.user"]}
    assert deposits_of(worker, "p0") == []
    assert deposits_of(worker, "p1") == []


def test_an_empty_batch_is_not_announced_at_all(worker):
    worker.subscribeTable("alice", table="glbl.user", page_id="p1")

    result = worker.notifyDbEvents("alice", dbevents={"glbl.user": []}, page_id="p1")

    assert result == {"tables": []}
    assert deposits_of(worker, "p1") == []


def test_local_only_deposits_on_the_origin_page_alone(worker):
    """The hidden transaction: its events belong to the page that made them."""
    worker.subscribeTable("alice", table="glbl.user", page_id="p1")

    result = worker.notifyDbEvents(
        "alice", dbevents={"glbl.user": ["ins:1"]}, page_id="p0", local_only=True
    )

    assert result == {"tables": ["glbl.user"]}
    assert [d["batch"] for d in deposits_of(worker, "p0")] == [["ins:1"]]
    assert deposits_of(worker, "p1") == []


# ----------------------------------------------------------------------
# The species never mix
# ----------------------------------------------------------------------


def test_the_deposit_drains_on_its_own_key_and_never_as_a_datachange(worker):
    worker.subscribeTable("alice", table="glbl.user", page_id="p1")
    worker.setStoreSubscription("alice", page_id="p1", storename="page", prefix="form")
    worker.notifyDbEvents("alice", dbevents={"glbl.user": ["ins:1"]}, page_id="p0")
    worker.page_register.get("p1")["store"]["form.name"] = "Ada"

    collected = worker.collect_page("p1")

    assert [d["table"] for d in collected["dbevents"]] == ["glbl.user"]
    assert [c["key"]["path"] for c in collected["datachanges"]] == ["form", "form.name"]
    assert deposits_of(worker, "p1") == []
