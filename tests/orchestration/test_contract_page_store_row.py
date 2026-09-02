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

"""Contract: the page store queue lives on the register row.

The page row carries ``datachanges`` and ``datachanges_idx``; the subscriber
``RegisterRegistry.subscribe_page_store`` attaches to the row's Bag fills them
with ``serverChange`` changes for the paths under ``subscribed_paths``. The
collector object is gone from the page row: its pending changes were an object
outside the parcel and were lost on freeze and transfer, while the queue as a
row field travels with the row.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker

WORKER_NAME = "standard_0001"


@pytest.fixture
def worker(tmp_path):
    deposit = FreezeHandler(tmp_path / "frozen_users")
    made = SpaWorker(WORKER_NAME, freeze_handler=deposit, deposit_lock_retry_interval=0.01)
    made.new_page("u1", page_id="p1", connection_id="s1")
    return made


@pytest.fixture
def page(worker):
    row = worker.page_register.get("p1")
    row["subscribed_paths"].add("form")
    return row


def test_a_write_under_a_subscribed_prefix_is_queued_as_a_serverchange(page):
    page["store"]["form.name"] = "Ada"

    assert len(page["datachanges"]) == 1
    change = page["datachanges"][0]
    assert change["key"] == {"path": "form.name", "reason": "serverChange", "fired": False}
    assert change["value"] == "Ada"
    assert change["delete"] is False
    assert change["change_idx"] == 1

    page["store"]["form.age"] = 36

    assert [c["key"]["path"] for c in page["datachanges"]] == ["form.name", "form.age"]
    assert page["datachanges"][-1]["change_idx"] == 2
    assert page["datachanges_idx"] == 2


def test_the_autocreated_parents_of_a_write_are_not_changes(page):
    page["subscribed_paths"].add("a")
    page["store"].set_item("a.b.c", 1)

    assert [c["key"]["path"] for c in page["datachanges"]] == ["a.b.c"]


def test_a_prefix_matches_on_segment_boundaries(page):
    page["store"]["form2.name"] = "Ada"

    assert page["datachanges"] == []


def test_a_write_outside_every_prefix_is_not_queued(page):
    page["store"]["other.name"] = "Ada"

    assert page["datachanges"] == []


def test_after_detach_page_a_write_queues_nothing(worker, page):
    worker.registry.detach_page(page)

    page["store"]["form.name"] = "Ada"

    assert page["datachanges"] == []


def test_a_page_born_with_a_queue_in_its_fields_keeps_it(worker):
    pending = [{"key": {"path": "form.name", "reason": "serverChange", "fired": False}}]

    woken = worker.new_page(
        "u1", page_id="p2", connection_id="s1", datachanges=pending, datachanges_idx=7
    )

    assert woken["datachanges"] == pending
    assert woken["datachanges_idx"] == 7


async def test_collect_page_returns_the_queue_and_leaves_the_row_empty(desk_lane):
    worker = desk_lane.worker
    worker.new_page("u1", page_id="p1", connection_id="s1")
    await desk_lane.verb(
        "setStoreSubscription", "u1", page_id="p1", storename="page", prefix="form"
    )
    row = worker.page_register.get("p1")
    row["store"]["form.name"] = "Ada"

    collected = await desk_lane.verb("collect_page", "p1")

    assert [c["key"]["path"] for c in collected["datachanges"]] == ["form.name"]
    assert [c["key"]["reason"] for c in collected["datachanges"]] == ["serverChange"]
    assert row["datachanges"] == []
    assert row["datachanges_idx"] == 0


async def test_two_requests_partition_the_queue_between_them(desk_lane):
    worker = desk_lane.worker
    worker.new_page("u1", page_id="p1", connection_id="s1")
    await desk_lane.verb("setStoreSubscription", "u1", page_id="p1", storename="page", prefix="srv")
    row = worker.page_register.get("p1")
    other = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xt-request-b")
    try:
        row["store"]["srv.a"] = 1
        row["store"]["srv.b"] = 2

        first = await desk_lane.verb_on(other, "collect_page", "p1")

        assert [c["key"]["path"] for c in first["datachanges"]] == ["srv.a", "srv.b"]

        row["store"]["srv.c"] = 3

        second = await desk_lane.verb("collect_page", "p1")

        assert [c["key"]["path"] for c in second["datachanges"]] == ["srv.c"]
    finally:
        other.shutdown(wait=True)


async def test_a_prefix_subscribed_after_birth_captures_the_next_write(desk_lane):
    worker = desk_lane.worker
    worker.new_page("u1", page_id="p1", connection_id="s1")
    row = worker.page_register.get("p1")
    row["store"]["late.name"] = "before"

    assert row["datachanges"] == []

    await desk_lane.verb(
        "setStoreSubscription", "u1", page_id="p1", storename="page", prefix="late"
    )
    row["store"]["late.name"] = "after"

    assert [c["key"]["path"] for c in row["datachanges"]] == ["late.name"]
