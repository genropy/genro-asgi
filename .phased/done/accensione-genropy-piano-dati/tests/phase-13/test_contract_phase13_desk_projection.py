"""Contract — Phase 13: the desk is a projection of the page rows.

Implementation tests (project rule 10) over a real lane (worker + commander
on a real UDS, the conftest fixture). Skeletons: replace each red body with a
real test of exactly what the wf:contract: lines state; names and contract
lines are read-only.
"""

import pytest


def test_freezing_a_user_clears_his_pages_at_the_desk():
    # wf:contract: a page subscribes a table through the lane; freezing its user
    # wf:contract: leaves NOTHING of the page at the vertex: no entry in the desk
    # wf:contract: subscription index, no datachange/dbevent queue, no
    # wf:contract: page_connection_map row — what waits for a frozen user is lost
    pytest.fail("phase 13 pending")


def test_adoption_rebuilds_the_desk_index_from_the_replayed_rows():
    # wf:contract: after freeze and adoption, WITHOUT any new subscribeTable,
    # wf:contract: a notifyDbEvents on the table the page had subscribed reaches
    # wf:contract: the woken page's next collect — the commander rebuilt the
    # wf:contract: index from the table_subscriptions the announcements carried
    pytest.fail("phase 13 pending")


def test_the_new_page_announcement_carries_the_rows_subscriptions():
    # wf:contract: the new_page worker event carries the row's
    # wf:contract: table_subscriptions — empty at birth, the replayed set at the
    # wf:contract: wake — and the vertex fold files exactly those entries
    pytest.fail("phase 13 pending")


def test_the_drop_cascade_reaches_the_desk_and_is_pinned():
    # wf:contract: drop_connection and drop_user clear the departed pages'
    # wf:contract: queues and index entries at the desk; the assertion must fail
    # wf:contract: if either cleanup call is removed (the panel's coverage gap)
    pytest.fail("phase 13 pending")
