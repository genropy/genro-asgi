"""Contract — Phase 14: unservable addresses are refused at the verb.

Implementation tests (project rule 10). Skeletons: replace each red body with
a real test of exactly what the wf:contract: lines state; names and contract
lines are read-only.
"""

import pytest


def test_a_state_kind_this_pass_does_not_deliver_is_refused_at_the_call():
    # wf:contract: set_datachange with kind='page_store' or 'connection_store'
    # wf:contract: raises an explicit error IN THE CALLER'S OWN CALL, before
    # wf:contract: anything lands on the request slot — never a silent success
    pytest.fail("phase 14 pending")


def test_a_filtered_address_fails_alone():
    # wf:contract: set_datachange with filters=... raises at the call; the
    # wf:contract: request's OTHER events (laid before and after) survive on the
    # wf:contract: slot and the same request's collect_page drains and delivers
    # wf:contract: them — the bad call fails alone, as the pre_refactoring does
    pytest.fail("phase 14 pending")


def test_nothing_refused_ever_reaches_the_desk():
    # wf:contract: after the refusals above, the desk queues hold nothing of the
    # wf:contract: refused messages — no half-filed batch, and the exchange of
    # wf:contract: the request completes without error
    pytest.fail("phase 14 pending")
