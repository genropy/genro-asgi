"""Contract — Phase 13: the desk is a projection of the page rows.

Implementation tests (project rule 10) over a real lane (worker + commander
on a real UDS, the conftest fixture). Skeletons: replace each red body with a
real test of exactly what the wf:contract: lines state; names and contract
lines are read-only.
"""

from __future__ import annotations

from genro_asgi.spa.orchestration.spa_worker import GUEST_PREFIX

from .conftest import wait_for


async def subscribed_guest(lane, table: str = "mytable") -> str:
    """A guest with one page whose subscription went through the lane.

    The vertex row placement would have created is seeded by hand: the lane
    has no reception in front of it.
    """
    lane.worker.add_connection("a1b2", sticky_cid="spa-a1b2")
    lane.worker.add_page("page-0", "a1b2")
    guest = f"{GUEST_PREFIX}a1b2"
    lane.commander.user_map[guest] = lane.commander._new_row()
    await lane.verb("subscribeTable", guest, table, "page-0")
    await wait_for(lambda: lane.worker.subscribed_tables == set(lane.desk.subscribed_tables))
    return guest


async def sent_events(lane) -> None:
    """Flush the worker's announcements to the vertex on the worker's own channel:
    the fold reads the envelope before the announcement is answered."""
    await lane.announce()


async def test_freezing_a_user_clears_his_pages_at_the_desk(desk_lane):
    # wf:contract: a page subscribes a table through the lane; freezing its user
    # wf:contract: leaves NOTHING of the page at the vertex: no entry in the desk
    # wf:contract: subscription index, no datachange/dbevent queue, no
    # wf:contract: page_connection_map row — what waits for a frozen user is lost
    guest = await subscribed_guest(desk_lane)
    await sent_events(desk_lane)
    assert "page-0" in desk_lane.commander.page_connection_map
    desk_lane.desk.file_dbevent(
        {"table": "mytable", "batch": [], "from_page_id": "px", "reason": None, "ts": 0.0}
    )

    assert await desk_lane.worker.freeze_user(guest) is True
    await sent_events(desk_lane)

    assert "page-0" not in desk_lane.desk.page_subscriptions.page_tables
    assert "page-0" not in desk_lane.desk.page_datachange_map
    assert "page-0" not in desk_lane.desk.page_dbevent_map
    assert "page-0" not in desk_lane.commander.page_connection_map


async def test_adoption_rebuilds_the_desk_index_from_the_replayed_rows(desk_lane):
    # wf:contract: after freeze and adoption, WITHOUT any new subscribeTable,
    # wf:contract: a notifyDbEvents on the table the page had subscribed reaches
    # wf:contract: the woken page's next collect — the commander rebuilt the
    # wf:contract: index from the table_subscriptions the announcements carried
    guest = await subscribed_guest(desk_lane)
    await sent_events(desk_lane)
    assert await desk_lane.worker.freeze_user(guest) is True
    await sent_events(desk_lane)
    assert desk_lane.desk.subscribed_tables == []

    await desk_lane.worker.adopt_connection(guest, "a1b2")
    await sent_events(desk_lane)
    assert desk_lane.desk.subscribed_tables == ["mytable"]

    await desk_lane.open_request()
    await desk_lane.verb("notifyDbEvents", guest, {"mytable": [{"dbevent": "I", "pkey": "r1"}]})
    delivery = await desk_lane.verb("collect_page", "page-0")
    assert [deposit["table"] for deposit in delivery["dbevents"]] == ["mytable"]


async def test_the_new_page_announcement_carries_the_rows_subscriptions(desk_lane):
    # wf:contract: the new_page worker event carries the row's
    # wf:contract: table_subscriptions — empty at birth, the replayed set at the
    # wf:contract: wake — and the vertex fold files exactly those entries
    # The births are read BEFORE the subscription: every round-trip on the wire
    # carries the pending announcements away, and the pushed source filter is one.
    desk_lane.worker.add_connection("a1b2", sticky_cid="spa-a1b2")
    desk_lane.worker.add_page("page-0", "a1b2")
    births = [event for event in desk_lane.worker.worker_events if event["op"] == "new_page"]
    assert [event["table_subscriptions"] for event in births] == [[]]

    guest = f"{GUEST_PREFIX}a1b2"
    desk_lane.commander.user_map[guest] = desk_lane.commander._new_row()
    await desk_lane.verb("subscribeTable", guest, "mytable", "page-0")
    await sent_events(desk_lane)
    assert await desk_lane.worker.freeze_user(guest) is True
    await sent_events(desk_lane)
    await desk_lane.wait_filter_synced()

    await desk_lane.worker.adopt_connection(guest, "a1b2")
    wakes = [event for event in desk_lane.worker.worker_events if event["op"] == "new_page"]
    assert [event["table_subscriptions"] for event in wakes] == [["mytable"]]
    await sent_events(desk_lane)
    assert desk_lane.desk.page_subscriptions.page_tables["page-0"] == {"mytable"}


async def test_the_drop_cascade_reaches_the_desk_and_is_pinned(desk_lane):
    # wf:contract: drop_connection and drop_user clear the departed pages'
    # wf:contract: queues and index entries at the desk; the assertion must fail
    # wf:contract: if either cleanup call is removed (the panel's coverage gap)
    commander, desk = desk_lane.commander, desk_lane.desk
    commander.connection_user_map["c-1"] = "mario"
    commander.user_map["mario"] = commander._new_row()
    commander.page_connection_map["p-1"] = "c-1"
    desk.op_subscribe_table("p-1", "mytable")
    desk.file_dbevent(
        {"table": "mytable", "batch": [], "from_page_id": "px", "reason": None, "ts": 0.0}
    )
    assert desk.page_dbevent_map["p-1"]

    commander.drop_connection("c-1")
    assert "p-1" not in desk.page_subscriptions.page_tables
    assert "p-1" not in desk.page_dbevent_map
    assert "p-1" not in commander.page_connection_map

    desk.user_store_change_map["mario"] = [{"key": {}, "value": 1}]
    commander.drop_user("mario")
    assert "mario" not in desk.user_store_change_map
