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

"""dbevents end to end: own ops, own index, own pipe, origin excluded.

The pool is real but in-process — two ``UserStickyWorker`` on the commander's own
hub over ``LocalChannel`` pairs — so a subscription really ascends, a commit is
really resolved on the cross-worker surface and really comes back down a
``/dbevents_in`` EVENT. What the tests pin down is §2.4: a co-located subscriber
is served with zero channel traffic, a remote one is served exactly once, the
origin worker's pages are never served twice, a table nobody subscribed costs no
send, and a deposit never enters the datachanges species.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import pytest
from genro_tytx import from_tytx

from genro_asgi.channel.local import LocalChannel
from genro_asgi.spa.commander import UserStickyCommander
from genro_asgi.spa.worker import UserStickyWorker

SETTLE_TIMEOUT = 5.0


async def until(predicate: Any, timeout: float = SETTLE_TIMEOUT) -> None:
    """Await a condition without blocking the loop."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise TimeoutError("condition never became true")
        await asyncio.sleep(0.01)


class Notified:
    """A commander with two in-process workers and every descending send recorded.

    The workers are wired exactly like spawned ones (a roster row with
    ``process=None``, a REGISTER over the channel, the same fold). ``sends``
    records what the commander pushes down, which is how "zero channel traffic"
    and "one send per worker" are asserted.
    """

    def __init__(self) -> None:
        self.commander = UserStickyCommander(workers=0, guest_occupancy_limit=1000)
        self.workers: dict[str, UserStickyWorker] = {}
        self.sends: list[tuple[str, str, Any]] = []

    async def start(self, count: int = 2) -> None:
        await self.commander.start()
        hub_post = self.commander.hub.post

        async def recording_post(name: str, path: str, data: Any = None) -> str:
            self.sends.append((name, path, data))
            return await hub_post(name, path, data)

        self.commander.hub.post = recording_post  # type: ignore[method-assign]
        for _ in range(count):
            await self.add_worker()

    async def add_worker(self) -> str:
        commander = self.commander
        name = commander.next_worker_name()
        commander.worker_roster[name] = commander.new_roster_row(os.getpid(), None)
        worker = UserStickyWorker(name)
        channel = LocalChannel(name)
        worker.attach_channel(channel)
        await channel.connect()
        await commander.hub.attach_local(channel)
        await worker.start()
        self.workers[name] = worker
        return name

    async def stop(self) -> None:
        await self.commander.stop()
        for worker in self.workers.values():
            await worker.shutdown()

    @property
    def names(self) -> list[str]:
        return list(self.workers)

    def worker_of(self, index: int) -> UserStickyWorker:
        return self.workers[self.names[index]]

    def dbevents_of(self, page_id: str, worker_index: int) -> list[dict[str, Any]]:
        return self.worker_of(worker_index).page_items.get(page_id)["dbevents"]

    async def new_page(self, user: str, page_id: str, worker_index: int) -> dict[str, Any]:
        """Create a page of ``user`` on a chosen worker, through the ordinary CALL."""
        self.commander.assign_user(user, self.names[worker_index])
        return await self.commander.forward_call(
            user, "/op/new_page", {"page_id": page_id, "session_id": f"s-{page_id}"}
        )

    async def subscribe(self, user: str, page_id: str, table: str, subscribe: bool = True) -> Any:
        """Subscribe a page to a table, waiting until the surface has folded it."""
        result = await self.commander.forward_call(
            user,
            "/op/subscribeTable",
            {"page_id": page_id, "table": table, "subscribe": subscribe},
        )
        wanted = page_id in self.commander.page_subscriptions.pages_for(table)
        await until(lambda: wanted == subscribe)
        return result

    async def notify(self, user: str, dbevents: dict[str, Any], **kwargs: Any) -> Any:
        """Announce a commit from ``user``'s own worker."""
        return await self.commander.forward_call(
            user, "/op/notifyDbEvents", {"dbevents": dbevents, **kwargs}
        )


@pytest.fixture
async def pool() -> Any:
    running = Notified()
    await running.start()
    try:
        yield running
    finally:
        await running.stop()


# ----------------------------------------------------------------------
# The subscription: local index first, then the cross-worker surface
# ----------------------------------------------------------------------


async def test_a_subscription_lands_on_both_indexes_and_on_the_row(pool: Notified) -> None:
    await pool.new_page("alice", "p1", 0)

    result = await pool.subscribe("alice", "p1", "glbl.user")

    assert result == {"page_id": "p1", "table": "glbl.user", "subscribe": True}
    worker = pool.worker_of(0)
    assert worker.subscriptions.pages_for("glbl.user") == {"p1"}
    assert worker.page_items.get("p1")["table_subscriptions"] == {"glbl.user"}
    assert pool.commander.page_subscriptions.pages_for("glbl.user") == {"p1"}


async def test_a_subscription_for_an_unknown_page_is_an_error(pool: Notified) -> None:
    await pool.new_page("alice", "p1", 0)

    with pytest.raises(Exception, match="unknown page"):
        await pool.commander.forward_call(
            "alice", "/op/subscribeTable", {"page_id": "ghost", "table": "glbl.user"}
        )


# ----------------------------------------------------------------------
# §2.4: local at once, remote once, the origin never twice
# ----------------------------------------------------------------------


async def test_a_local_subscriber_is_served_with_zero_channel_traffic(pool: Notified) -> None:
    await pool.new_page("alice", "p0", 0)
    await pool.new_page("alice", "p1", 0)
    await pool.subscribe("alice", "p1", "glbl.user")
    pool.sends.clear()

    await pool.notify("alice", {"glbl.user": ["ins:1"]}, reason="commit", page_id="p0")

    deposits = pool.dbevents_of("p1", 0)
    assert [(d["table"], d["batch"], d["from_page_id"], d["reason"]) for d in deposits] == [
        ("glbl.user", ["ins:1"], "p0", "commit")
    ]
    # The subscriber sat on the producer's own worker: nothing went down the rail.
    assert pool.sends == []


async def test_the_origin_pages_own_deposit_rides_the_reply_of_its_notify(
    pool: Notified,
) -> None:
    """The commit's own page is a subscriber like any other — and it is CALLing."""
    await pool.new_page("alice", "p1", 0)
    await pool.subscribe("alice", "p1", "glbl.user")

    envelope = await pool.commander.forward_envelope(
        "alice",
        "/op/notifyDbEvents",
        {"dbevents": {"glbl.user": ["ins:1"]}, "page_id": "p1"},
    )

    assert [d["table"] for d in from_tytx(envelope["dbevents"], "json")] == ["glbl.user"]
    # Drained by that very REPLY: the deposit was made and delivered in one cycle.
    assert pool.dbevents_of("p1", 0) == []


async def test_a_remote_subscriber_is_served_once_down_its_own_pipe(pool: Notified) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.subscribe("bob", "p2", "glbl.user")
    pool.sends.clear()

    await pool.notify("alice", {"glbl.user": ["ins:1"]}, page_id="p1")

    await until(lambda: pool.dbevents_of("p2", 1))
    assert [d["batch"] for d in pool.dbevents_of("p2", 1)] == [["ins:1"]]
    assert [(name, path) for name, path, _ in pool.sends] == [(pool.names[1], "/dbevents_in")]
    batch = pool.sends[0][2]
    assert [item["page_id"] for item in batch] == ["p2"]


async def test_the_origin_workers_pages_are_not_served_twice(pool: Notified) -> None:
    await pool.new_page("alice", "p0", 0)
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("alice", "p2", 0)
    await pool.new_page("bob", "p3", 1)
    for user, page_id in (("alice", "p1"), ("alice", "p2"), ("bob", "p3")):
        await pool.subscribe(user, page_id, "glbl.user")
    pool.sends.clear()

    await pool.notify("alice", {"glbl.user": ["ins:1"]}, page_id="p0")

    await until(lambda: pool.dbevents_of("p3", 1))
    # The origin worker served p1 and p2 itself; the commander skipped both.
    assert [len(pool.dbevents_of(page_id, 0)) for page_id in ("p1", "p2")] == [1, 1]
    assert [(name, path) for name, path, _ in pool.sends] == [(pool.names[1], "/dbevents_in")]
    assert [item["page_id"] for item in pool.sends[0][2]] == ["p3"]


async def test_pages_of_one_worker_share_a_single_send(pool: Notified) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.new_page("bob", "p3", 1)
    for page_id in ("p2", "p3"):
        await pool.subscribe("bob", page_id, "glbl.user")
    pool.sends.clear()

    await pool.notify("alice", {"glbl.user": ["ins:1"]}, page_id="p1")

    await until(lambda: pool.dbevents_of("p3", 1))
    assert len(pool.sends) == 1
    assert sorted(item["page_id"] for item in pool.sends[0][2]) == ["p2", "p3"]


async def test_the_deposit_is_shaped_once_so_every_page_reads_the_same_ts(
    pool: Notified,
) -> None:
    await pool.new_page("alice", "p0", 0)
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.subscribe("alice", "p1", "glbl.user")
    await pool.subscribe("bob", "p2", "glbl.user")

    await pool.notify("alice", {"glbl.user": ["ins:1"]}, page_id="p0")

    await until(lambda: pool.dbevents_of("p2", 1))
    local = pool.dbevents_of("p1", 0)[0]
    remote = pool.dbevents_of("p2", 1)[0]
    assert local["ts"] == remote["ts"]
    assert local == remote


# ----------------------------------------------------------------------
# What costs nothing, and what stops
# ----------------------------------------------------------------------


async def test_a_commit_nobody_subscribed_costs_no_fan_out(pool: Notified) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    pool.sends.clear()

    result = await pool.notify("alice", {"glbl.user": ["ins:1"]}, page_id="p1")

    assert result == {"tables": ["glbl.user"]}
    assert pool.sends == []
    assert pool.dbevents_of("p1", 0) == []
    assert pool.dbevents_of("p2", 1) == []


async def test_an_empty_batch_is_not_announced_at_all(pool: Notified) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.subscribe("alice", "p1", "glbl.user")

    result = await pool.notify("alice", {"glbl.user": []}, page_id="p1")

    assert result == {"tables": []}
    assert pool.dbevents_of("p1", 0) == []
    assert pool.worker_of(0).outbox.pending() == 0


async def test_an_unsubscribe_stops_the_delivery_on_both_sides(pool: Notified) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("bob", "p2", 1)
    await pool.subscribe("alice", "p1", "glbl.user")
    await pool.subscribe("bob", "p2", "glbl.user")

    await pool.subscribe("alice", "p1", "glbl.user", subscribe=False)
    await pool.subscribe("bob", "p2", "glbl.user", subscribe=False)
    pool.sends.clear()
    await pool.notify("alice", {"glbl.user": ["ins:1"]}, page_id="p1")

    assert pool.worker_of(0).page_items.get("p1")["table_subscriptions"] == set()
    assert pool.dbevents_of("p1", 0) == []
    assert pool.sends == []


async def test_a_dropped_page_leaves_no_subscription_behind(pool: Notified) -> None:
    await pool.new_page("alice", "p1", 0)
    await pool.new_page("alice", "p2", 0)
    await pool.subscribe("alice", "p1", "glbl.user")

    await pool.commander.forward_call("alice", "/op/drop_page", {"page_id": "p1"})

    await until(lambda: not pool.commander.page_subscriptions.pages_for("glbl.user"))
    assert pool.worker_of(0).subscriptions.pages_for("glbl.user") == set()


async def test_a_page_that_left_the_destination_loses_its_deposit(
    pool: Notified, caplog: pytest.LogCaptureFixture
) -> None:
    """The batch was already on the wire when the page went away."""
    destination = pool.worker_of(1)
    deposit = destination.dbevent_deposit("glbl.user", ["ins:1"], "p1", None)

    with caplog.at_level(logging.DEBUG, logger="genro_asgi.spa.worker"):
        await destination.apply_dbevents_in([{"page_id": "p9", "deposit": deposit}])

    assert "dbevent dropped" in caplog.text


# ----------------------------------------------------------------------
# The species never mix: the deposit rides its own REPLY key
# ----------------------------------------------------------------------


async def test_a_deposit_leaves_on_the_dbevents_key_and_never_as_a_datachange(
    pool: Notified,
) -> None:
    await pool.new_page("alice", "p0", 0)
    await pool.new_page("alice", "p1", 0)
    await pool.subscribe("alice", "p1", "glbl.user")
    await pool.notify("alice", {"glbl.user": ["ins:1"]}, page_id="p0")
    page = pool.worker_of(0).page_items.get("p1")
    page["store"]["form.name"] = "Ada"

    envelope = await pool.commander.forward_envelope(
        "alice", "/op/subscribeTable", {"page_id": "p1", "table": "glbl.user"}
    )

    dbevents = from_tytx(envelope["dbevents"], "json")
    datachanges = from_tytx(envelope["datachanges"], "json")
    assert [d["table"] for d in dbevents] == ["glbl.user"]
    assert [c["key"]["path"] for c in datachanges] == ["form", "form.name"]
    # Drained: the page's pending list is empty and nothing was duplicated.
    assert page["dbevents"] == []
