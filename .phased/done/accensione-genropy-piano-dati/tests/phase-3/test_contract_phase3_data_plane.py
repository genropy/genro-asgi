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
``setStoreSubscription`` :1432). Local form only: the target page lives on this
worker — addressing pages of other workers and ``filters`` broadcasts are the
second pass, but the SIGNATURE already carries ``kind``, ``target`` and
``filters`` (Must-not-break line 2: local is one branch of an addressing
decision, not its absence).
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


def test_collect_page_merges_both_collectors_by_ts(worker):
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    worker.setStoreSubscription("u1", page_id="p1", storename="user", prefix="prefs")
    page = worker.page_register.get("p1")
    page["store"]["form.name"] = "Ada"
    worker.user_register.get("u1")["store"]["prefs.theme"] = "dark"
    page["store"]["form.age"] = 36

    collected = worker.collect_page("p1")

    assert [c["key"]["path"] for c in collected["datachanges"]] == [
        "form",
        "form.name",
        "prefs",
        "prefs.theme",
        "form.age",
    ]
    assert collected["dbevents"] == []
    assert worker.collect_page("p1")["datachanges"] == []


def test_collect_page_drains_the_dbevents_species_apart(worker):
    page = worker.page_register.get("p1")
    page["dbevents"].append({"table": "adm.user"})

    collected = worker.collect_page("p1")

    assert collected["dbevents"] == [{"table": "adm.user"}]
    assert collected["datachanges"] == []
    assert worker.collect_page("p1")["dbevents"] == []


def test_collect_page_of_an_unknown_page_is_an_error(worker):
    with pytest.raises(KeyError, match="nope"):
        worker.collect_page("nope")


# ----------------------------------------------------------------------
# set_datachange, local form: the explicit deposit lands whatever the filter says
# ----------------------------------------------------------------------


def test_the_explicit_deposit_ignores_the_page_filter(worker):
    worker.set_datachange("u1", change=foreign_change("untold.x", 1), target="p1")

    page = worker.page_register.get("p1")
    assert [c["key"]["path"] for c in page["collector"].drain()] == ["untold.x"]


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


def test_replace_coalesces_the_pending_change_of_the_same_key(worker):
    """The daemon's own dedup: a value written over and over reaches the browser once."""
    worker.set_datachange("u1", change=foreign_change("untold.x", 1), target="p1", replace=True)
    worker.set_datachange("u1", change=foreign_change("untold.x", 2), target="p1", replace=True)

    changes = worker.collect_page("p1")["datachanges"]
    assert [c["key"]["path"] for c in changes] == ["untold.x"]
    assert changes[0]["value"] == 2


def test_reset_datachanges_empties_the_pending_without_reading_them(worker):
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    worker.page_register.get("p1")["store"]["form.name"] = "Ada"

    worker.reset_datachanges("u1", target="p1")

    assert worker.collect_page("p1")["datachanges"] == []


def test_drop_datachanges_discards_only_the_path_it_names(worker):
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="other")
    page = worker.page_register.get("p1")
    page["store"]["form.name"] = "Ada"
    page["store"]["other.kept"] = "stays"

    worker.drop_datachanges("u1", path="form", target="p1")

    paths = [c["key"]["path"] for c in worker.collect_page("p1")["datachanges"]]
    assert "form.name" not in paths
    assert "other.kept" in paths
