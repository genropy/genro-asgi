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
"""

from __future__ import annotations

import pytest


# ----------------------------------------------------------------------
# The index: fed by the immediate subscription call
# ----------------------------------------------------------------------


def test_a_subscription_call_updates_the_index_before_it_answers():
    # wf:contract: the worker's subscribeTable sends a CALL on the lane; when
    # wf:contract: that call returns, the commander's table->pages index
    # wf:contract: already holds the entry — subscribe-then-commit inside the
    # wf:contract: same request finds the table active (the window is closed).
    pytest.fail("phase 8 pending")


def test_an_unsubscribe_call_removes_the_entry_and_stops_future_delivery():
    # wf:contract: after the unsubscribe call returns, events announced for
    # wf:contract: that table are no longer queued for that page.
    pytest.fail("phase 8 pending")


# ----------------------------------------------------------------------
# The exchange: events in, pendings out, one round
# ----------------------------------------------------------------------


def test_the_exchange_returns_the_callers_own_events_in_the_same_round():
    # wf:contract: the end-of-request exchange carries the events the request
    # wf:contract: generated; the commander sorts them into the queues FIRST
    # wf:contract: and answers AFTER, so the reply already contains the
    # wf:contract: caller's own events for the tables its page subscribes.
    pytest.fail("phase 8 pending")


def test_events_for_another_pages_queue_wait_for_that_pages_own_exchange():
    # wf:contract: events sorted into a sibling page's queue are NOT pushed:
    # wf:contract: they come back in the reply of that page's own next
    # wf:contract: exchange, and the queue is emptied by it.
    pytest.fail("phase 8 pending")


def test_every_exchange_reply_carries_the_subscribed_table_names():
    # wf:contract: the reply of every exchange carries the current list of
    # wf:contract: table names holding at least one subscription — the
    # wf:contract: worker's source filter cache (registro §4).
    pytest.fail("phase 8 pending")


def test_an_event_for_a_table_nobody_subscribes_dies_at_the_desk():
    # wf:contract: an arriving event whose table has no subscriber anywhere is
    # wf:contract: discarded at the commander — no queue grows for it.
    pytest.fail("phase 8 pending")


def test_replace_coalesces_inside_the_target_queue():
    # wf:contract: a datachange sent with replace=True drops the pending change
    # wf:contract: of the same key (path, reason, fired) already sitting in the
    # wf:contract: target page's queue, so the browser reads the value once —
    # wf:contract: the daemon's own dedup, now applied at the desk.
    pytest.fail("phase 8 pending")


# ----------------------------------------------------------------------
# Hygiene: the age threshold and the fold
# ----------------------------------------------------------------------


def test_events_older_than_the_threshold_are_discarded():
    # wf:contract: every queued event carries its timestamp; events older than
    # wf:contract: the configured age (a parameter with a default) are removed
    # wf:contract: and never delivered — the notify_user criterion: a stale
    # wf:contract: delivery is garbage. One rule for all three queue species.
    pytest.fail("phase 8 pending")


def test_a_dropped_page_takes_its_queue_with_it():
    # wf:contract: the drop_page fold the commander already runs clears that
    # wf:contract: page's queue and its subscription entries in the same
    # wf:contract: breath — nothing is delivered to a page that is gone.
    pytest.fail("phase 8 pending")
