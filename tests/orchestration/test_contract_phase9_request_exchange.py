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

"""Phase 9 contract: the worker's side — request slot, exchange, merged collect.

The worker's half of the redesign (registro 2026-08-20 §2, §5, §6, §7): events
born during a request accumulate on a slot of THAT request; at the end of the
request — always, even with nothing to send — one exchange on the lane delivers
them to the commander and retires the page's pendings plus the user's STATE
store writes. The site-facing verb signatures DO NOT MOVE: they are the
pre_refactoring's, already pinned by the phase-3/4 contract files, whose
delivery-mechanism assertions this phase rewrites with the implementation they
photograph (foreman decision, notes.md).

What dies: ``deposit_dbevent``, ``fan_out_local``, ``worker.subscriptions``
(the local index), the ``dbevents`` mailbox on the page item.
"""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor

import pytest
from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_tytx import to_tytx

from genro_asgi.spa.orchestration.spa_worker import RequestSlot
from genro_asgi.spa.orchestration.worker_handler import PING_OP_PATH

from .conftest import wait_for

USER = "alice"
PAGE = "p1"
SIBLING = "p0"
TABLE = "glbl.user"


@pytest.fixture
async def lane(desk_lane):
    """The live lane with alice's two pages already on the worker."""
    desk_lane.worker.new_page(USER, page_id=SIBLING, connection_id="s1")
    desk_lane.worker.new_page(USER, page_id=PAGE, connection_id="s1")
    # The desk judges a target's existence at the vertex: a ping's REPLY carries
    # the births up, and the fold reads the envelope before it answers.
    await desk_lane.worker_handler.connector.call(PING_OP_PATH)
    return desk_lane


def foreign_change(path: str, value):
    """A change born elsewhere, TYTX-encoded the way the site hands it over."""
    source = Bag()
    producer = DataChangeCollector(source)
    source[path] = value
    return to_tytx(producer.drain()[-1], "json")


async def on_thread(pool, work):
    """Run one of the worker's verbs on a thread of its own — another request."""
    return await asyncio.get_running_loop().run_in_executor(pool, work)


# ----------------------------------------------------------------------
# The slot and the source filter
# ----------------------------------------------------------------------


async def test_events_of_a_request_accumulate_on_that_requests_own_slot(lane):
    # wf:contract: notifyDbEvents during a request shapes the deposits (table,
    # wf:contract: batch, from_page_id, reason, ts — the pre_refactoring shape)
    # wf:contract: and lays them on the CURRENT request's slot; two requests
    # wf:contract: served in parallel threads never see each other's slot.
    await lane.verb("subscribeTable", USER, table=TABLE, page_id=PAGE)
    await lane.wait_filter_synced()
    await lane.open_request()
    await lane.verb(
        "notifyDbEvents", USER, dbevents={TABLE: ["ins:1"]}, reason="commit", page_id=SIBLING
    )

    slot = await asyncio.get_running_loop().run_in_executor(
        lane.request_pool, lambda: lane.worker.request_slot
    )
    assert [(d["table"], d["batch"], d["from_page_id"], d["reason"]) for d in slot.dbevents] == [
        (TABLE, ["ins:1"], SIBLING, "commit")
    ]
    assert isinstance(slot.dbevents[0]["ts"], float)

    with ThreadPoolExecutor(max_workers=1) as other_request:
        other = await on_thread(other_request, lambda: lane.worker.request_slot)
    assert isinstance(other, RequestSlot)
    assert other.dbevents == []


async def test_events_for_tables_outside_the_cache_die_in_the_worker(lane):
    # wf:contract: the worker filters at the source with the subscribed-table
    # wf:contract: names the commander pushes: an event for a table not in that
    # wf:contract: set is dropped before the wire.
    await lane.verb("subscribeTable", USER, table=TABLE, page_id=PAGE)
    await wait_for(lambda: lane.worker.subscribed_tables == {TABLE})

    answer = await lane.verb(
        "notifyDbEvents", USER, dbevents={"nobody.wants": ["ins:1"]}, page_id=PAGE
    )

    assert answer == {"tables": []}
    slot = await asyncio.get_running_loop().run_in_executor(
        lane.request_pool, lambda: lane.worker.request_slot
    )
    assert slot.dbevents == []
    assert lane.desk.page_dbevent_map == {}


async def test_local_only_events_reach_only_the_own_collect_and_never_the_wire(lane):
    # wf:contract: notifyDbEvents(local_only=True) — the hidden transaction —
    # wf:contract: keeps its deposits on the request slot for the calling
    # wf:contract: page's own collect alone: nothing is sent to the commander,
    # wf:contract: no other page ever sees them.
    await lane.verb("subscribeTable", USER, table=TABLE, page_id=SIBLING)
    await lane.wait_filter_synced()
    await lane.verb(
        "notifyDbEvents", USER, dbevents={TABLE: ["ins:1"]}, page_id=PAGE, local_only=True
    )

    collected = await lane.verb("collect_page", PAGE)

    assert [d["batch"] for d in collected["dbevents"]] == [["ins:1"]]
    # Nothing was filed at the desk, so the subscriber never hears of it.
    assert lane.desk.page_dbevent_map == {}
    assert (await lane.verb("collect_page", SIBLING))["dbevents"] == []


# ----------------------------------------------------------------------
# The exchange at the end of the request
# ----------------------------------------------------------------------


async def test_the_exchange_happens_on_every_request_even_empty_handed(lane):
    # wf:contract: a request that generated nothing still exchanges at its
    # wf:contract: end: retiring the page's pendings is the reason, and the
    # wf:contract: outbound payload is simply empty.
    served = []
    desk = lane.desk
    original = desk.op_exchange
    desk.op_exchange = functools.partial(_recording_exchange, original, served)

    collected = await lane.verb("collect_page", PAGE)

    assert collected == {"datachanges": [], "dbevents": []}
    assert served == [{"page_id": PAGE, "user": USER, "dbevents": []}]


def _recording_exchange(original, served, **payload):
    """Serve the real exchange, keeping the payload the worker sent up."""
    served.append(payload)
    return original(**payload)


async def test_own_generated_events_come_back_in_the_same_requests_collect(lane):
    # wf:contract: a request that deposits an event for a table its own page
    # wf:contract: subscribes finds that event in its own response's dbevents —
    # wf:contract: same call, not the next one (the desk sorts before
    # wf:contract: answering; phase-8 twin, asserted end to end here).
    await lane.verb("subscribeTable", USER, table=TABLE, page_id=PAGE)
    await lane.wait_filter_synced()
    await lane.verb("notifyDbEvents", USER, dbevents={TABLE: ["ins:1"]}, page_id=PAGE)

    collected = await lane.verb("collect_page", PAGE)

    assert [d["batch"] for d in collected["dbevents"]] == [["ins:1"]]


async def test_collect_merges_own_collectors_with_the_retired_pendings(lane):
    # wf:contract: the response's datachanges merge the page's own captured
    # wf:contract: changes (its row and its user_view, still local) with the
    # wf:contract: datachanges retired from the commander, in ARRIVAL order —
    # wf:contract: the order one list would have had; dbevents stay their own
    # wf:contract: species, never mixed.
    worker = lane.worker
    await lane.verb("setStoreSubscription", USER, page_id=PAGE, storename="page", prefix="form")
    await lane.verb("setStoreSubscription", USER, page_id=PAGE, storename="user", prefix="prefs")
    await lane.verb("subscribeTable", USER, table=TABLE, page_id=PAGE)
    await lane.wait_filter_synced()
    worker.page_register.get(PAGE)["store"]["form.name"] = "Ada"
    worker.user_register.get(USER)["store"]["prefs.theme"] = "dark"
    # A change that crosses the wire keeps its change_ts to the millisecond (TYTX
    # rounds there), so the gap is what makes the intended order unambiguous.
    await asyncio.sleep(0.005)
    await lane.verb(
        "set_datachange", USER, change=foreign_change("untold.x", 1), target=PAGE
    )
    await lane.verb("notifyDbEvents", USER, dbevents={TABLE: ["ins:1"]}, page_id=PAGE)

    collected = await lane.verb("collect_page", PAGE)

    paths = [c["key"]["path"] for c in collected["datachanges"]]
    assert paths == ["form.name", "prefs", "prefs.theme", "untold.x"]
    assert [c["change_ts"] for c in collected["datachanges"]] == sorted(
        c["change_ts"] for c in collected["datachanges"]
    )
    assert [d["batch"] for d in collected["dbevents"]] == [["ins:1"]]


# ----------------------------------------------------------------------
# Addressed writes: one road, through the desk
# ----------------------------------------------------------------------


async def test_set_datachange_to_a_page_of_the_caller_lands_on_its_row(lane):
    # wf:contract: set_datachange keeps its full pre_refactoring signature
    # wf:contract: (identity, change, kind=, target=, filters=, replace=) and
    # wf:contract: a page of the CALLER'S OWN user living here is written on
    # wf:contract: its row at once, never through the desk (D-DC4).
    answer = await lane.verb(
        "set_datachange",
        USER,
        change=foreign_change("untold.x", 1),
        kind="page",
        target=PAGE,
        filters=None,
        replace=False,
    )

    assert answer == {
        "kind": "page",
        "target": PAGE,
        "filters": None,
        "replace": False,
        "local": True,
        "filed": True,
    }
    assert [c["key"]["path"] for c in lane.worker.page_register.get(PAGE)["datachanges"]] == [
        "untold.x"
    ]
    collected = await lane.verb("collect_page", PAGE)
    assert [c["key"]["path"] for c in collected["datachanges"]] == ["untold.x"]
    assert lane.desk.page_datachange_map == {}


async def test_a_user_store_write_is_applied_before_the_collect_of_the_retriever(lane):
    # wf:contract: STATE writes retired by the exchange are applied to the
    # wf:contract: user's own store Bag first (apply_forwarded, _original_ts
    # wf:contract: stamped), THEN the collect runs: the retrieving page reads
    # wf:contract: the captured change in the same response, and the sibling
    # wf:contract: pages — every connection, one shared Bag — capture it on
    # wf:contract: their own user_view for their own next drain.
    worker = lane.worker
    await lane.verb("setStoreSubscription", USER, page_id=PAGE, storename="user", prefix="prefs")
    await lane.verb(
        "setStoreSubscription", USER, page_id=SIBLING, storename="user", prefix="prefs"
    )
    await lane.verb("collect_page", PAGE)
    await lane.verb("collect_page", SIBLING)
    await lane.verb(
        "set_datachange",
        USER,
        change=foreign_change("prefs.theme", "dark"),
        kind="user_store",
        target=USER,
    )

    collected = await lane.verb("collect_page", PAGE)

    written = [c for c in collected["datachanges"] if c["key"]["path"] == "prefs.theme"]
    assert [c["value"] for c in written] == ["dark"]
    assert worker.user_register.get(USER)["store"]["prefs.theme"] == "dark"
    assert "_original_ts" in worker.user_register.get(USER)["store"].get_attr("prefs.theme")
    # The sibling captured the very same Bag write on its own user_view.
    sibling = await lane.verb("collect_page", SIBLING)
    assert [c["key"]["path"] for c in sibling["datachanges"] if c["value"] == "dark"] == [
        "prefs.theme"
    ]


async def test_the_dead_helpers_are_gone(lane):
    # wf:contract: deposit_dbevent, fan_out_local and the worker's local
    # wf:contract: subscription index no longer exist on SpaWorker, and the
    # wf:contract: page item carries no dbevents mailbox — events never touch
    # wf:contract: the registry.
    worker = lane.worker
    assert not hasattr(worker, "deposit_dbevent")
    assert not hasattr(worker, "fan_out_local")
    assert not hasattr(worker, "subscriptions")
    assert not hasattr(worker, "_addressed_row")
    await lane.verb("subscribeTable", USER, table=TABLE, page_id=PAGE)
    await lane.wait_filter_synced()
    await lane.verb("notifyDbEvents", USER, dbevents={TABLE: ["ins:1"]}, page_id=PAGE)
    await lane.verb("collect_page", PAGE)
    # The row's mailbox — kept alive by the pre_refactoring worker, which shares
    # the registry — is never written nor read by this worker any more.
    assert worker.page_register.get(PAGE)["dbevents"] == []
