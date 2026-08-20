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

"""Phase 3 contract: the local data plane — subscriptions, deposit, drain.

Derived from ``tests/test_spa_stores.py`` (setStoreSubscription, the two
collectors, collect_page) and the pre_refactoring signatures
(``src/genro_asgi/spa/worker.py``: ``collect_page`` :1142, ``set_datachange``
:1358, ``reset_datachanges`` :1395, ``drop_datachanges`` :1411,
``setStoreSubscription`` :1432). The SIGNATURES are pinned here and DO NOT
move — ``kind``, ``target`` and ``filters`` are in them already (Must-not-break
line 2: local is one branch of an addressing decision, not its absence).

**Amended by Phase 9** (foreman decision, notes.md): the delivery mechanism
these tests photographed — the addressed write landing straight on the target's
own collector, the ``dbevents`` mailbox on the page row — is dead. Every
addressed write now travels to the commander's desk and comes back through the
end-of-request exchange, so the tests that watched the local collector watch the
delivery instead. What stays purely local is the page's own capture: its
collector and its ``user_view``, the page listening to itself.
"""

from __future__ import annotations

import pytest
from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_tytx import to_tytx

from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker

WORKER_NAME = "standard_0001"


@pytest.fixture
def worker(tmp_path):
    deposit = FreezeHandler(tmp_path / "frozen_users")
    made = SpaWorker(WORKER_NAME, freeze_handler=deposit, deposit_lock_retry_interval=0.01)
    made.new_page("u1", page_id="p1", session_id="s1")
    return made


def foreign_change(path: str, value):
    """A change born elsewhere, TYTX-encoded the way the site hands it over."""
    source = Bag()
    producer = DataChangeCollector(source)
    source[path] = value
    return to_tytx(producer.drain()[-1], "json")


# ----------------------------------------------------------------------
# setStoreSubscription: the page declares what it wants to hear about
# ----------------------------------------------------------------------


def test_the_page_collector_captures_nothing_until_the_page_subscribes(worker):
    page = worker.page_register.get("p1")
    page["store"]["form.name"] = "Ada"
    assert page["collector"].pending == 0
    assert page["subscribed_paths"] == set()


def test_the_page_subscription_opens_and_closes_its_own_store(worker):
    page = worker.page_register.get("p1")

    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    page["store"]["form.name"] = "Ada"
    assert [c["key"]["path"] for c in page["collector"].drain()] == ["form", "form.name"]

    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form", active=False)
    assert page["subscribed_paths"] == set()
    page["store"]["form.name"] = "Grace"
    assert page["collector"].pending == 0


def test_the_user_subscription_opens_the_view_and_widens_it(worker):
    page = worker.page_register.get("p1")
    user_store = worker.user_register.get("u1")["store"]

    worker.setStoreSubscription("u1", page_id="p1", storename="user", prefix="gnr.chat.msg")
    view = page["user_view"]
    assert page["store_subscriptions"] == {"gnr.chat.msg"}
    user_store["gnr.chat.msg.m1"] = "ciao"
    assert [c["key"]["path"] for c in view.drain()] == ["gnr.chat.msg", "gnr.chat.msg.m1"]

    worker.setStoreSubscription("u1", page_id="p1", storename="user", prefix="gnr.batch")
    assert page["user_view"] is view
    assert view.paths == {"gnr.chat.msg", "gnr.batch"}


def test_closing_a_user_subscription_a_page_never_took_is_a_no_op(worker):
    worker.setStoreSubscription("u1", page_id="p1", storename="user", prefix="prefs", active=False)

    assert worker.page_register.get("p1")["user_view"] is None


def test_an_unknown_storename_is_an_error(worker):
    with pytest.raises(ValueError, match="connection"):
        worker.setStoreSubscription("u1", page_id="p1", storename="connection", prefix="x")


def test_a_subscription_for_an_unknown_page_is_an_error(worker):
    with pytest.raises(KeyError, match="ghost"):
        worker.setStoreSubscription("u1", page_id="ghost", storename="page", prefix="x")


# ----------------------------------------------------------------------
# collect_page: one drain point, two species, merged by change_ts
# ----------------------------------------------------------------------


async def test_collect_page_merges_both_collectors_by_ts(desk_lane):
    worker = desk_lane.worker
    worker.new_page("u1", page_id="p1", session_id="s1")
    await desk_lane.verb(
        "setStoreSubscription", "u1", page_id="p1", storename="page", prefix="form"
    )
    await desk_lane.verb(
        "setStoreSubscription", "u1", page_id="p1", storename="user", prefix="prefs"
    )
    page = worker.page_register.get("p1")
    page["store"]["form.name"] = "Ada"
    worker.user_register.get("u1")["store"]["prefs.theme"] = "dark"
    page["store"]["form.age"] = 36

    collected = await desk_lane.verb("collect_page", "p1")

    assert [c["key"]["path"] for c in collected["datachanges"]] == [
        "form",
        "form.name",
        "prefs",
        "prefs.theme",
        "form.age",
    ]
    assert collected["dbevents"] == []
    assert (await desk_lane.verb("collect_page", "p1"))["datachanges"] == []


async def test_collect_page_drains_the_dbevents_species_apart(desk_lane):
    """The mailbox on the row is gone: the deposits come back from the desk."""
    worker = desk_lane.worker
    worker.new_page("u1", page_id="p1", session_id="s1")
    await desk_lane.verb("subscribeTable", "u1", table="adm.user", page_id="p1")
    await desk_lane.verb("notifyDbEvents", "u1", dbevents={"adm.user": ["ins:1"]}, page_id="p1")

    collected = await desk_lane.verb("collect_page", "p1")

    assert [d["table"] for d in collected["dbevents"]] == ["adm.user"]
    assert collected["datachanges"] == []
    assert (await desk_lane.verb("collect_page", "p1"))["dbevents"] == []


def test_collect_page_of_an_unknown_page_is_an_error(worker):
    with pytest.raises(KeyError, match="nope"):
        worker.collect_page("nope")


# ----------------------------------------------------------------------
# set_datachange, local form: the explicit deposit lands whatever the filter says
# ----------------------------------------------------------------------


async def test_the_explicit_deposit_ignores_the_page_filter(desk_lane):
    """An explicit write is not a capture: it lands whatever the page subscribed."""
    desk_lane.worker.new_page("u1", page_id="p1", session_id="s1")
    await desk_lane.verb(
        "set_datachange", "u1", change=foreign_change("untold.x", 1), target="p1"
    )

    collected = await desk_lane.verb("collect_page", "p1")

    assert [c["key"]["path"] for c in collected["datachanges"]] == ["untold.x"]


def test_the_signature_carries_the_addressing_it_will_grow_into(worker):
    """Must-not-break line 2: ``kind``, ``target`` and ``filters`` are already
    in the signature — the local branch is a routing decision, not a smaller verb."""
    answer = worker.set_datachange(
        "u1", change=foreign_change("untold.x", 1), target="p1", filters=None, replace=False
    )

    assert answer["target"] == "p1"
    assert answer["filters"] is None
    assert answer["replace"] is False
    assert "kind" in answer


async def test_replace_coalesces_the_pending_change_of_the_same_key(desk_lane):
    """The daemon's own dedup, now in the desk queue: written twice, delivered once."""
    desk_lane.worker.new_page("u1", page_id="p1", session_id="s1")
    for value in (1, 2):
        await desk_lane.verb(
            "set_datachange",
            "u1",
            change=foreign_change("untold.x", value),
            target="p1",
            replace=True,
        )

    changes = (await desk_lane.verb("collect_page", "p1"))["datachanges"]
    assert [c["key"]["path"] for c in changes] == ["untold.x"]
    assert changes[0]["value"] == 2


async def test_reset_datachanges_empties_the_pending_without_reading_them(desk_lane):
    """What it empties is the desk queue: the addressed writes waiting for that page."""
    desk_lane.worker.new_page("u1", page_id="p1", session_id="s1")
    await desk_lane.verb(
        "set_datachange", "u1", change=foreign_change("untold.x", 1), target="p1"
    )
    await desk_lane.verb("reset_datachanges", "u1", target="p1")

    assert (await desk_lane.verb("collect_page", "p1"))["datachanges"] == []


async def test_drop_datachanges_discards_only_the_path_it_names(desk_lane):
    desk_lane.worker.new_page("u1", page_id="p1", session_id="s1")
    await desk_lane.verb(
        "set_datachange", "u1", change=foreign_change("form.name", "Ada"), target="p1"
    )
    await desk_lane.verb(
        "set_datachange", "u1", change=foreign_change("other.kept", "stays"), target="p1"
    )
    await desk_lane.verb("drop_datachanges", "u1", path="form", target="p1")

    collected = await desk_lane.verb("collect_page", "p1")
    paths = [c["key"]["path"] for c in collected["datachanges"]]
    assert "form.name" not in paths
    assert "other.kept" in paths
