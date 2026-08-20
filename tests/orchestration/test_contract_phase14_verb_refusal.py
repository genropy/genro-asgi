"""Contract — Phase 14: unservable addresses are refused at the verb.

Implementation tests (project rule 10). Skeletons: replace each red body with
a real test of exactly what the wf:contract: lines state; names and contract
lines are read-only.
"""

from __future__ import annotations

import pytest
from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_tytx import to_tytx


def foreign_change(path: str, value):
    """A change born elsewhere, TYTX-encoded the way the site hands it over."""
    source = Bag()
    producer = DataChangeCollector(source)
    source[path] = value
    return to_tytx(producer.drain()[-1], "json")


async def test_a_state_kind_this_pass_does_not_deliver_is_refused_at_the_call(desk_lane):
    # wf:contract: set_datachange with kind='page_store' or 'connection_store'
    # wf:contract: raises an explicit error IN THE CALLER'S OWN CALL, before
    # wf:contract: anything lands on the request slot — never a silent success
    desk_lane.worker.new_page("u1", page_id="p1", session_id="s1")
    await desk_lane.open_request()

    for kind in ("page_store", "connection_store"):
        with pytest.raises(NotImplementedError, match=kind):
            await desk_lane.verb(
                "set_datachange", "u1", change=foreign_change("x.y", 1), kind=kind, target="p1"
            )
    slots = await desk_lane.verb("collect_page", "p1")
    assert slots["datachanges"] == []


async def test_a_filtered_address_fails_alone(desk_lane):
    # wf:contract: set_datachange with filters=... raises at the call; the
    # wf:contract: request's OTHER events (laid before and after) survive on the
    # wf:contract: slot and the same request's collect_page drains and delivers
    # wf:contract: them — the bad call fails alone, as the pre_refactoring does
    desk_lane.worker.new_page("u1", page_id="p1", session_id="s1")
    await desk_lane.open_request()

    await desk_lane.verb("set_datachange", "u1", change=foreign_change("before.x", 1), target="p1")
    with pytest.raises(NotImplementedError, match="filtered"):
        await desk_lane.verb(
            "set_datachange", "u1", change=foreign_change("bad.x", 2), filters="user:alice"
        )
    await desk_lane.verb("set_datachange", "u1", change=foreign_change("after.x", 3), target="p1")

    delivery = await desk_lane.verb("collect_page", "p1")
    assert [c["key"]["path"] for c in delivery["datachanges"]] == ["before.x", "after.x"]


async def test_nothing_refused_ever_reaches_the_desk(desk_lane):
    # wf:contract: after the refusals above, the desk queues hold nothing of the
    # wf:contract: refused messages — no half-filed batch, and the exchange of
    # wf:contract: the request completes without error
    desk_lane.worker.new_page("u1", page_id="p1", session_id="s1")
    await desk_lane.open_request()

    with pytest.raises(NotImplementedError):
        await desk_lane.verb(
            "set_datachange", "u1", change=foreign_change("bad.x", 2), filters="user:alice"
        )
    with pytest.raises(KeyError, match="ghost"):
        await desk_lane.verb(
            "set_datachange", "u1", change=foreign_change("bad.y", 3), target="ghost"
        )
    with pytest.raises(KeyError):
        await desk_lane.verb("reset_datachanges", "u1")

    delivery = await desk_lane.verb("collect_page", "p1")
    assert delivery["datachanges"] == []
    assert desk_lane.desk.page_datachange_map == {}
    assert desk_lane.desk.user_store_change_map == {}
