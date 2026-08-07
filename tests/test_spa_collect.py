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

"""The drain rides the REPLY: pull delivery to the client.

Exercised over a real wire (a ``LocalChannel`` on a ``ChannelHub``) and, for the
passthrough, over the commander in the single role — so the payload asserted
here is the one a page really reads, TYTX-encoded and hydrated back with
``from_tytx``. What the tests pin down is the pull rule:
a page-addressed CALL comes back carrying that page's pending under its two
species keys, a CALL addressing no page carries neither, and nothing is ever
pushed — a page that does not call keeps its changes in its collector.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from genro_routes import route

from genro_tytx import from_tytx

from genro_asgi.channel import ChannelCallError, ChannelHub, Frame, LocalChannel
from genro_asgi.spa.commander import UserStickyCommander
from genro_asgi.spa.worker import UserStickyWorker

SETTLE_TIMEOUT = 5.0


class PageWorker(UserStickyWorker):
    """A worker with the two page-addressed op forms an application would have."""

    @route()
    def page_ping(self, identity: str, page_id: str) -> dict[str, Any]:
        """The ordinary applicative CALL: it addresses a page and succeeds."""
        return {"identity": identity, "page_id": page_id}

    @route()
    def page_boom(self, identity: str, page_id: str) -> None:
        """A page-addressed CALL that fails: the drain must not depend on it."""
        raise RuntimeError("handler exploded")

    @route()
    def plain_ping(self, identity: str) -> dict[str, Any]:
        """A CALL that addresses no page at all."""
        return {"identity": identity}


class CollectHarness:
    """A ``PageWorker`` on a LocalChannel attached to a hub, payloads kept raw."""

    def __init__(self) -> None:
        self.worker = PageWorker("W:w1")
        self.hub = ChannelHub()
        self.channel = LocalChannel(self.worker.name)

    async def start(self) -> None:
        await self.hub.start()
        self.worker.attach_channel(self.channel)
        await self.channel.connect()
        await self.hub.attach_local(self.channel)

    async def stop(self) -> None:
        await self.worker.shutdown()
        await self.hub.stop()

    async def call(self, path: str, kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
        """CALL the worker and hand back the REPLY payload untouched."""
        payload = await self.hub.call(
            self.worker.name,
            path,
            {"identity": "u1", "kwargs": kwargs or {}},
            timeout=SETTLE_TIMEOUT,
        )
        return dict(payload)


@pytest.fixture
async def harness() -> Any:
    probe = CollectHarness()
    await probe.start()
    try:
        yield probe
    finally:
        await probe.stop()


def delivered(payload: dict[str, Any], key: str) -> Any:
    """Hydrate one delivery key the way the client side will."""
    return from_tytx(payload[key], "json")


def make_page(worker: UserStickyWorker, page_id: str = "p1") -> dict[str, Any]:
    """One user with one page subscribed to a prefix of its user store."""
    worker.registry.new_page(page_id, user="u1", session_id="s1")
    return worker.registry.subscribe_store_path(page_id, "prefs")


# ----------------------------------------------------------------------
# The page-addressed REPLY carries the drain
# ----------------------------------------------------------------------


async def test_a_page_call_comes_back_with_its_pending_merged_by_ts(
    harness: CollectHarness,
) -> None:
    page = make_page(harness.worker)
    page["store"]["form.name"] = "Ada"
    harness.worker.user_items.get("u1")["store"]["prefs.theme"] = "dark"
    page["dbevents"].append({"table": "sys.user", "batch": [], "reason": "test"})

    payload = await harness.call("/op/page_ping", {"page_id": "p1"})

    assert payload["result"] == {"identity": "u1", "page_id": "p1"}
    changes = delivered(payload, "datachanges")
    paths = [change["key"]["path"] for change in changes]
    # Both collectors drained into one list, ordered by capture instant: the
    # page's own store first, then the view on the user store.
    assert paths == ["form", "form.name", "prefs", "prefs.theme"]
    assert [change["change_ts"] for change in changes] == sorted(
        change["change_ts"] for change in changes
    )
    assert delivered(payload, "dbevents") == [
        {"table": "sys.user", "batch": [], "reason": "test"}
    ]


async def test_the_drain_resets_what_it_delivered(harness: CollectHarness) -> None:
    page = make_page(harness.worker)
    page["store"]["form.name"] = "Ada"
    page["dbevents"].append({"table": "sys.user", "batch": [], "reason": "test"})

    first = await harness.call("/op/page_ping", {"page_id": "p1"})
    second = await harness.call("/op/page_ping", {"page_id": "p1"})

    assert delivered(first, "datachanges") and delivered(first, "dbevents")
    assert delivered(second, "datachanges") == []
    assert delivered(second, "dbevents") == []
    assert page["collector"].pending == 0


async def test_a_failing_page_call_still_delivers(harness: CollectHarness) -> None:
    page = make_page(harness.worker)
    page["store"]["form.name"] = "Ada"

    payload = await harness.call("/op/page_boom", {"page_id": "p1"})

    assert payload["error"].startswith("RuntimeError")
    assert "result" not in payload
    assert [change["key"]["path"] for change in delivered(payload, "datachanges")] == [
        "form",
        "form.name",
    ]


async def test_a_non_page_call_carries_neither_key(harness: CollectHarness) -> None:
    page = make_page(harness.worker)
    page["store"]["form.name"] = "Ada"

    payload = await harness.call("/op/plain_ping")

    assert "datachanges" not in payload
    assert "dbevents" not in payload
    # Nothing was pushed and nothing was drained: it waits for the page's own call.
    assert page["collector"].pending == 2


async def test_an_unknown_page_carries_neither_key(harness: CollectHarness) -> None:
    make_page(harness.worker)

    payload = await harness.call("/op/page_ping", {"page_id": "gone"})

    assert "datachanges" not in payload
    assert "dbevents" not in payload


# ----------------------------------------------------------------------
# The commander carries the two keys through, untouched
# ----------------------------------------------------------------------


@pytest.fixture
async def single() -> Any:
    """A commander in the single role, holding a ``PageWorker`` in this process."""
    commander = UserStickyCommander(
        workers=0,
        local_worker=True,
        worker_class=f"{__name__}:PageWorker",
        guest_occupancy_limit=1000,
    )
    await commander.start()
    try:
        yield commander
    finally:
        await commander.stop()


async def test_the_commander_passes_the_delivery_through(single: UserStickyCommander) -> None:
    page = make_page(single.worker)
    page["store"]["form.name"] = "Ada"
    page["dbevents"].append({"table": "sys.user", "batch": [], "reason": "test"})

    envelope = await single.forward_envelope("u1", "/op/page_ping", {"page_id": "p1"})

    assert envelope["result"] == {"identity": "u1", "page_id": "p1"}
    assert [change["key"]["path"] for change in delivered(envelope, "datachanges")] == [
        "form",
        "form.name",
    ]
    assert delivered(envelope, "dbevents") == [
        {"table": "sys.user", "batch": [], "reason": "test"}
    ]


async def test_a_failing_forward_still_carries_the_delivery(single: UserStickyCommander) -> None:
    """The op outcome does not gate the drain — on the commander path too.

    The worker attaches the delivery to its error REPLY; the commander must not
    throw it away while raising: the whole REPLY rides the exception's
    ``payload``, so the response layer can still deliver what was drained.
    """
    page = make_page(single.worker)
    page["store"]["form.name"] = "Ada"
    page["dbevents"].append({"table": "sys.user", "batch": [], "reason": "test"})

    with pytest.raises(ChannelCallError) as excinfo:
        await single.forward_envelope("u1", "/op/page_boom", {"page_id": "p1"})

    payload = excinfo.value.payload
    assert [change["key"]["path"] for change in delivered(payload, "datachanges")] == [
        "form",
        "form.name",
    ]
    assert delivered(payload, "dbevents") == [
        {"table": "sys.user", "batch": [], "reason": "test"}
    ]
    # Drained once, lost never: the collectors are empty, the exception has it all.
    assert page["collector"].pending == 0


async def test_forward_call_still_answers_the_result_alone(single: UserStickyCommander) -> None:
    make_page(single.worker)

    result = await single.forward_call("u1", "/op/page_ping", {"page_id": "p1"})

    assert result == {"identity": "u1", "page_id": "p1"}


async def test_a_non_page_forward_brings_no_delivery_keys(single: UserStickyCommander) -> None:
    envelope = await single.forward_envelope("u1", "/op/plain_ping")

    assert envelope == {"result": {"identity": "u1"}}


def test_the_delivery_keys_are_the_two_species() -> None:
    from genro_asgi.spa.worker import DELIVERY_KEYS

    assert DELIVERY_KEYS == ("datachanges", "dbevents")


async def test_nothing_is_pushed_between_calls(harness: CollectHarness) -> None:
    """No EVENT carries a datachange: delivery happens only on a REPLY."""
    events: list[Frame] = []
    harness.hub.on_event = lambda member, frame: events.append(frame)
    page = make_page(harness.worker)
    page["store"]["form.name"] = "Ada"
    await asyncio.sleep(0.05)

    assert events == []
    assert page["collector"].pending == 2
