"""Contract — Phase 12: the carried store re-attaches every user_view.

Implementation tests (project rule 10): they photograph the adoption path of
the new worker. Skeletons: replace each red body with a real test of exactly
what the wf:contract: lines state; names and contract lines are read-only.
"""

from __future__ import annotations

from genro_bag import Bag

from genro_asgi.spa.orchestration.spa_worker import GUEST_PREFIX


def watching_guest(lane) -> str:
    """A guest with one page holding a user-store window on ``gnr.batch``."""
    lane.worker.add_connection("a1b2")
    lane.worker.add_page("page-0", "a1b2")
    guest = f"{GUEST_PREFIX}a1b2"
    lane.worker.setStoreSubscription(guest, "page-0", "user", "gnr.batch")
    return guest


async def test_a_page_still_captures_its_user_store_after_the_deposit_round_trip(desk_lane):
    # wf:contract: a guest page opens a user-store window (setStoreSubscription
    # wf:contract: storename='user'), the connection is re-labeled onto a real
    # wf:contract: identity (change_connection_user), frozen (freeze_connection)
    # wf:contract: and adopted back (adopt_connection); a subsequent write on the
    # wf:contract: user row's store Bag is captured by the page's user_view and
    # wf:contract: comes back from collect_page — the window is alive, not deaf
    watching_guest(desk_lane)
    desk_lane.worker.change_connection_user("a1b2", "mario")
    await desk_lane.worker.freeze_connection("a1b2")
    await desk_lane.worker.adopt_connection("mario", "a1b2")

    desk_lane.worker.user_register.get("mario")["store"]["gnr.batch.b1"] = "running"

    await desk_lane.open_request()
    delivery = await desk_lane.verb("collect_page", "page-0")
    assert "gnr.batch.b1" in [change["key"]["path"] for change in delivery["datachanges"]]


async def test_the_views_watch_the_rows_current_store_bag_after_adoption(desk_lane):
    # wf:contract: after adopt_connection installs the carried store, every
    # wf:contract: user_view of every page of the user observes the SAME Bag
    # wf:contract: object the user row holds — no view left on an orphan Bag
    watching_guest(desk_lane)
    desk_lane.worker.add_page("page-1", "a1b2")
    desk_lane.worker.setStoreSubscription(f"{GUEST_PREFIX}a1b2", "page-1", "user", "gnr.other")
    desk_lane.worker.change_connection_user("a1b2", "mario")
    await desk_lane.worker.freeze_connection("a1b2")
    await desk_lane.worker.adopt_connection("mario", "a1b2")

    row_store = desk_lane.worker.user_register.get("mario")["store"]
    for page_id in ("page-0", "page-1"):
        view = desk_lane.worker.page_register.get(page_id)["user_view"]
        assert view is not None and view.bag is row_store


async def test_no_captured_change_is_lost_in_the_swap(desk_lane):
    # wf:contract: changes the just-born view captured before the carried store
    # wf:contract: replaced the row's Bag are re-fed to the re-attached view,
    # wf:contract: so the next collect_page drains them — the pre_refactoring's
    # wf:contract: own guarantee (adopt_carried_store, spa/worker.py:2333)
    watching_guest(desk_lane)
    desk_lane.worker.change_connection_user("a1b2", "mario")
    # Captured by the view while it still watches the row's pre-swap Bag.
    desk_lane.worker.user_register.get("mario")["store"]["gnr.batch.b0"] = "queued"

    carried = Bag()
    carried["cart.item"] = "a lamp"
    with desk_lane.worker.dispatch_lock:
        desk_lane.worker._install_carried_store("mario", carried, False)
    # Captured by the re-attached view on the carried Bag.
    desk_lane.worker.user_register.get("mario")["store"]["gnr.batch.b1"] = "running"

    await desk_lane.open_request()
    delivery = await desk_lane.verb("collect_page", "page-0")
    paths = [change["key"]["path"] for change in delivery["datachanges"]]
    assert paths.index("gnr.batch.b0") < paths.index("gnr.batch.b1")
