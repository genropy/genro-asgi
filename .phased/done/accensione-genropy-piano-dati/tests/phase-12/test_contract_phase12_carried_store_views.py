"""Contract — Phase 12: the carried store re-attaches every user_view.

Implementation tests (project rule 10): they photograph the adoption path of
the new worker. Skeletons: replace each red body with a real test of exactly
what the wf:contract: lines state; names and contract lines are read-only.
"""

import pytest


def test_a_page_still_captures_its_user_store_after_the_deposit_round_trip():
    # wf:contract: a guest page opens a user-store window (setStoreSubscription
    # wf:contract: storename='user'), the connection is re-labeled onto a real
    # wf:contract: identity (change_connection_user), frozen (freeze_connection)
    # wf:contract: and adopted back (adopt_connection); a subsequent write on the
    # wf:contract: user row's store Bag is captured by the page's user_view and
    # wf:contract: comes back from collect_page — the window is alive, not deaf
    pytest.fail("phase 12 pending")


def test_the_views_watch_the_rows_current_store_bag_after_adoption():
    # wf:contract: after adopt_connection installs the carried store, every
    # wf:contract: user_view of every page of the user observes the SAME Bag
    # wf:contract: object the user row holds — no view left on an orphan Bag
    pytest.fail("phase 12 pending")


def test_no_captured_change_is_lost_in_the_swap():
    # wf:contract: changes the just-born view captured before the carried store
    # wf:contract: replaced the row's Bag are re-fed to the re-attached view,
    # wf:contract: so the next collect_page drains them — the pre_refactoring's
    # wf:contract: own guarantee (adopt_carried_store, spa/worker.py:2333)
    pytest.fail("phase 12 pending")
