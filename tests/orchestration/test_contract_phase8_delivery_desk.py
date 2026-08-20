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

"""Phase 8 contract: the commander's delivery desk.

The centre of the redesign (registro 2026-08-20 §2-§5, §7): the commander alone
holds the subscription index (table -> page ids) and the pending queues — per
page (two species: datachanges and dbevents, never mixed) and per user (STATE
writes to his store). Everything is fed and drained by CALLs on the phase-7
lane. Queues live OUTSIDE the pickled surface: events are ephemeral.

Derived from ``tests/test_spa_dbevents.py`` where behaviour carries over
(subscription answered, unsubscribe stops delivery, empty batches ignored,
origin semantics) and from the dictated design where it does not.


**How the calls are placed here.** The verbs the site calls — ``subscribeTable``
and the end-of-request exchange — are the WORKER's half and belong to Phase 9;
what this phase built is the desk and the rung the call climbs. So the tests
place the desk CALLs themselves, on a real lane over a real UDS: a ``SpaWorker``
on one end, a real ``WorkerHandler`` under a real ``SpaCommander`` on the other.
The assertions are the contract's, taken at the layer that owns them.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from genro_tytx import from_tytx, to_tytx

from genro_asgi.spa.orchestration import FreezeHandler, GroupHandler, SpaCommander, SpaWorker
from genro_asgi.spa.orchestration import spa_worker as spa_worker_module
from genro_asgi.spa.orchestration.spa_commander import DESK_PATH_PREFIX
from genro_asgi.spa.orchestration.worker_handler import WorkerHandler

WORKER_NAME = "standard_0001"
SUBSCRIBE_PATH = f"{DESK_PATH_PREFIX}subscribe_table"
EXCHANGE_PATH = f"{DESK_PATH_PREFIX}exchange"
USER = "mario"
PAGE = "page_one"
SIBLING = "page_two"


class XT_DeskLane:
    """A worker and its real handler on one UDS, the desk at the top of it.

    Args:
        commander: the vertex whose desk the calls reach.
        group: the group the handler hangs under.
        freeze_handler: the deposit the worker is built with.
    """

    def __init__(
        self, commander: SpaCommander, group: GroupHandler, freeze_handler: FreezeHandler
    ) -> None:
        self.commander = commander
        self.worker_handler = WorkerHandler(group, WORKER_NAME, **group.worker_settings)
        self.worker = SpaWorker(WORKER_NAME, freeze_handler=freeze_handler)
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def desk(self) -> Any:
        """The desk the calls of this lane land on."""
        return self.commander.delivery_desk

    async def open(self) -> None:
        """Bind, connect, present, and put the worker's read loop on the air."""
        connector = self.worker_handler.connector
        await connector.start()
        reader, writer = await asyncio.open_unix_connection(str(connector.socket_path))
        self.worker.attach_stream(spa_worker_module.FrameStream(reader, writer))
        await self.worker.send_presentation({})
        self._reader_task = asyncio.create_task(self.worker.receive_frames())
        await connector.wait_connected()

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self.worker.exit_process()
        await self.worker_handler.connector.stop()

    async def subscribe(self, page_id: str, table: str, subscribe: bool = True) -> Any:
        """Place the subscription call the way ``subscribeTable`` will place it."""
        return await self.worker.call(
            SUBSCRIBE_PATH, {"page_id": page_id, "table": table, "subscribe": subscribe}
        )

    async def exchange(
        self,
        page_id: str = PAGE,
        user: str = USER,
        datachanges: list[dict[str, Any]] | None = None,
        dbevents: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Place the end-of-request exchange, and decode what comes back."""
        answer = await self.worker.call(
            EXCHANGE_PATH,
            {
                "page_id": page_id,
                "user": user,
                "datachanges": datachanges,
                "dbevents": dbevents,
            },
        )
        return {
            "datachanges": from_tytx(answer["datachanges"], "json"),
            "dbevents": answer["dbevents"],
            "store_changes": from_tytx(answer["store_changes"], "json"),
            "tables": answer["tables"],
        }


@pytest.fixture
async def lane(short_root, tmp_path):
    commander = SpaCommander(short_root / "frozen_users")
    group = GroupHandler(
        commander,
        "standard",
        memory_concession_bytes=8 * 1024 * 1024 * 1024,
        instance_dir=short_root / "i",
        frozen_users_path=short_root / "frozen_users",
        entry_module="never.launched",
    )
    built = XT_DeskLane(commander, group, FreezeHandler(tmp_path / "frozen_users"))
    await built.open()
    yield built
    await built.close()


def a_change(path: str, value: Any, reason: str | None = None, age: float = 0.0) -> dict[str, Any]:
    """One change dict in the shape the collectors produce it."""
    return {
        "key": {"path": path, "reason": reason, "fired": False},
        "value": value,
        "attributes": None,
        "delete": False,
        "change_ts": datetime.now(UTC) - timedelta(seconds=age),
        "change_idx": 0,
    }


def addressed(
    target: str, change: dict[str, Any], kind: str = "page", replace: bool = False
) -> dict[str, Any]:
    """The header the worker wraps a change in, with the parcel it never opens."""
    return {
        "kind": kind,
        "target": target,
        "filters": None,
        "change": to_tytx(change, "json"),
        "replace": replace,
    }


def a_deposit(table: str, reason: str | None = None, age: float = 0.0) -> dict[str, Any]:
    """One table-event deposit in the shape ``dbevent_deposit`` gives it."""
    return {
        "table": table,
        "batch": [{"pkey": "1"}],
        "from_page_id": PAGE,
        "reason": reason,
        "ts": time.time() - age,
    }


# ----------------------------------------------------------------------
# The index: fed by the immediate subscription call
# ----------------------------------------------------------------------


async def test_a_subscription_call_updates_the_index_before_it_answers(lane):
    # wf:contract: the worker's subscribeTable sends a CALL on the lane; when
    # wf:contract: that call returns, the commander's table->pages index
    # wf:contract: already holds the entry — subscribe-then-commit inside the
    # wf:contract: same request finds the table active (the window is closed).
    answer = await asyncio.wait_for(lane.subscribe(PAGE, "invoices"), 5.0)
    assert lane.desk.page_subscriptions.pages_for("invoices") == {PAGE}
    # The answer itself carries the table: the index was written before it was composed.
    assert answer["tables"] == ["invoices"]
    assert answer["page_id"] == PAGE and answer["subscribe"] is True


async def test_an_unsubscribe_call_removes_the_entry_and_stops_future_delivery(lane):
    # wf:contract: after the unsubscribe call returns, events announced for
    # wf:contract: that table are no longer queued for that page.
    await asyncio.wait_for(lane.subscribe(PAGE, "invoices"), 5.0)
    answer = await asyncio.wait_for(lane.subscribe(PAGE, "invoices", subscribe=False), 5.0)
    assert answer["tables"] == []
    assert lane.desk.page_subscriptions.pages_for("invoices") == set()
    exchanged = await asyncio.wait_for(
        lane.exchange(dbevents=[a_deposit("invoices")]), 5.0
    )
    assert exchanged["dbevents"] == []
    assert lane.desk.page_dbevent_map == {}


# ----------------------------------------------------------------------
# The exchange: events in, pendings out, one round
# ----------------------------------------------------------------------


async def test_the_exchange_returns_the_callers_own_events_in_the_same_round(lane):
    # wf:contract: the end-of-request exchange carries the events the request
    # wf:contract: generated; the commander sorts them into the queues FIRST
    # wf:contract: and answers AFTER, so the reply already contains the
    # wf:contract: caller's own events for the tables its page subscribes.
    await asyncio.wait_for(lane.subscribe(PAGE, "invoices"), 5.0)
    exchanged = await asyncio.wait_for(
        lane.exchange(
            datachanges=[addressed(PAGE, a_change("form.name", "Mario"))],
            dbevents=[a_deposit("invoices", reason="commit")],
        ),
        5.0,
    )
    assert [deposit["table"] for deposit in exchanged["dbevents"]] == ["invoices"]
    assert exchanged["dbevents"][0]["reason"] == "commit"
    assert [change["value"] for change in exchanged["datachanges"]] == ["Mario"]
    # Retired: the queues are empty, nothing comes back twice.
    assert await asyncio.wait_for(lane.exchange(), 5.0) == {
        "datachanges": [],
        "dbevents": [],
        "store_changes": [],
        "tables": ["invoices"],
    }


async def test_events_for_another_pages_queue_wait_for_that_pages_own_exchange(lane):
    # wf:contract: events sorted into a sibling page's queue are NOT pushed:
    # wf:contract: they come back in the reply of that page's own next
    # wf:contract: exchange, and the queue is emptied by it.
    await asyncio.wait_for(lane.subscribe(SIBLING, "invoices"), 5.0)
    mine = await asyncio.wait_for(
        lane.exchange(
            datachanges=[addressed(SIBLING, a_change("form.name", "Mario"))],
            dbevents=[a_deposit("invoices")],
        ),
        5.0,
    )
    assert mine["datachanges"] == [] and mine["dbevents"] == []
    assert lane.desk.page_dbevent_map[SIBLING] and lane.desk.page_datachange_map[SIBLING]
    theirs = await asyncio.wait_for(lane.exchange(page_id=SIBLING), 5.0)
    assert [change["value"] for change in theirs["datachanges"]] == ["Mario"]
    assert [deposit["table"] for deposit in theirs["dbevents"]] == ["invoices"]
    assert SIBLING not in lane.desk.page_dbevent_map
    assert SIBLING not in lane.desk.page_datachange_map


async def test_every_exchange_reply_carries_the_subscribed_table_names(lane):
    # wf:contract: the reply of every exchange carries the current list of
    # wf:contract: table names holding at least one subscription — the
    # wf:contract: worker's source filter cache (registro §4).
    assert (await asyncio.wait_for(lane.exchange(), 5.0))["tables"] == []
    await asyncio.wait_for(lane.subscribe(PAGE, "invoices"), 5.0)
    await asyncio.wait_for(lane.subscribe(SIBLING, "customers"), 5.0)
    assert (await asyncio.wait_for(lane.exchange(), 5.0))["tables"] == [
        "customers",
        "invoices",
    ]
    await asyncio.wait_for(lane.subscribe(SIBLING, "customers", subscribe=False), 5.0)
    assert (await asyncio.wait_for(lane.exchange(), 5.0))["tables"] == ["invoices"]


async def test_an_event_for_a_table_nobody_subscribes_dies_at_the_desk(lane):
    # wf:contract: an arriving event whose table has no subscriber anywhere is
    # wf:contract: discarded at the commander — no queue grows for it.
    await asyncio.wait_for(lane.subscribe(PAGE, "invoices"), 5.0)
    exchanged = await asyncio.wait_for(lane.exchange(dbevents=[a_deposit("orders")]), 5.0)
    assert exchanged["dbevents"] == []
    assert lane.desk.page_dbevent_map == {}


async def test_replace_coalesces_inside_the_target_queue(lane):
    # wf:contract: a datachange sent with replace=True drops the pending change
    # wf:contract: of the same key (path, reason, fired) already sitting in the
    # wf:contract: target page's queue, so the browser reads the value once —
    # wf:contract: the daemon's own dedup, now applied at the desk.
    await asyncio.wait_for(
        lane.exchange(
            datachanges=[
                addressed(SIBLING, a_change("form.name", "first")),
                addressed(SIBLING, a_change("form.name", "second"), replace=True),
                addressed(SIBLING, a_change("form.other", "kept"), replace=True),
            ]
        ),
        5.0,
    )
    theirs = await asyncio.wait_for(lane.exchange(page_id=SIBLING), 5.0)
    assert [(c["key"]["path"], c["value"]) for c in theirs["datachanges"]] == [
        ("form.name", "second"),
        ("form.other", "kept"),
    ]


# ----------------------------------------------------------------------
# Hygiene: the age threshold and the fold
# ----------------------------------------------------------------------


async def test_events_older_than_the_threshold_are_discarded(lane):
    # wf:contract: every queued event carries its timestamp; events older than
    # wf:contract: the configured age (a parameter with a default) are removed
    # wf:contract: and never delivered — the notify_user criterion: a stale
    # wf:contract: delivery is garbage. One rule for all three queue species.
    stale = lane.desk.event_max_age_seconds + 60.0
    await asyncio.wait_for(lane.subscribe(PAGE, "invoices"), 5.0)
    exchanged = await asyncio.wait_for(
        lane.exchange(
            datachanges=[
                addressed(PAGE, a_change("form.old", "gone", age=stale)),
                addressed(PAGE, a_change("form.new", "kept")),
                addressed(USER, a_change("prefs.old", "gone", age=stale), kind="user_store"),
                addressed(USER, a_change("prefs.new", "kept"), kind="user_store"),
            ],
            dbevents=[a_deposit("invoices", reason="old", age=stale), a_deposit("invoices")],
        ),
        5.0,
    )
    assert [c["value"] for c in exchanged["datachanges"]] == ["kept"]
    assert [c["value"] for c in exchanged["store_changes"]] == ["kept"]
    assert [deposit["reason"] for deposit in exchanged["dbevents"]] == [None]


async def test_a_dropped_page_takes_its_queue_with_it(lane):
    # wf:contract: the drop_page fold the commander already runs clears that
    # wf:contract: page's queue and its subscription entries in the same
    # wf:contract: breath — nothing is delivered to a page that is gone.
    await asyncio.wait_for(lane.subscribe(PAGE, "invoices"), 5.0)
    await asyncio.wait_for(
        lane.exchange(
            page_id=SIBLING,
            datachanges=[addressed(PAGE, a_change("form.name", "Mario"))],
            dbevents=[a_deposit("invoices")],
        ),
        5.0,
    )
    assert lane.desk.page_datachange_map[PAGE] and lane.desk.page_dbevent_map[PAGE]
    lane.commander.drop_page(PAGE)
    assert PAGE not in lane.desk.page_datachange_map
    assert PAGE not in lane.desk.page_dbevent_map
    assert lane.desk.page_subscriptions.tables_for(PAGE) == set()
    assert lane.desk.subscribed_tables == []
