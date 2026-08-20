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

"""Phase 9 contract: the worker's side — request slot, exchange, merged collect.

The worker's half of the redesign (registro 2026-08-20 §2, §5, §6, §7): events
born during a request accumulate on a slot of THAT request; at the end of the
request — always, even with nothing to send — one exchange on the lane delivers
them to the commander and retires the page's pendings plus the user's STATE
store writes. The site-facing verb signatures DO NOT MOVE: they are the
pre_refactoring's, already pinned by the phase-3/4 contract files, whose
delivery-mechanism assertions this phase rewrites with the implementation they
photograph (foreman decision, notes.md).

What dies: ``deposit_dbevent``, ``fan_out_local``, ``worker.subscriptions``
(the local index), the ``dbevents`` mailbox on the page item.
"""

from __future__ import annotations

import pytest


# ----------------------------------------------------------------------
# The slot and the source filter
# ----------------------------------------------------------------------


def test_events_of_a_request_accumulate_on_that_requests_own_slot():
    # wf:contract: notifyDbEvents during a request shapes the deposits (table,
    # wf:contract: batch, from_page_id, reason, ts — the pre_refactoring shape)
    # wf:contract: and lays them on the CURRENT request's slot; two requests
    # wf:contract: served in parallel threads never see each other's slot.
    pytest.fail("phase 9 pending")


def test_events_for_tables_outside_the_cache_die_in_the_worker():
    # wf:contract: the worker filters at the source with the subscribed-table
    # wf:contract: names cache the last exchange reply carried: an event for a
    # wf:contract: table not in the cache is dropped before the wire.
    pytest.fail("phase 9 pending")


def test_local_only_events_reach_only_the_own_collect_and_never_the_wire():
    # wf:contract: notifyDbEvents(local_only=True) — the hidden transaction —
    # wf:contract: keeps its deposits on the request slot for the calling
    # wf:contract: page's own collect alone: nothing is sent to the commander,
    # wf:contract: no other page ever sees them.
    pytest.fail("phase 9 pending")


# ----------------------------------------------------------------------
# The exchange at the end of the request
# ----------------------------------------------------------------------


def test_the_exchange_happens_on_every_request_even_empty_handed():
    # wf:contract: a request that generated nothing still exchanges at its
    # wf:contract: end: retiring the page's pendings is the reason, and the
    # wf:contract: outbound payload is simply empty.
    pytest.fail("phase 9 pending")


def test_own_generated_events_come_back_in_the_same_requests_collect():
    # wf:contract: a request that deposits an event for a table its own page
    # wf:contract: subscribes finds that event in its own response's dbevents —
    # wf:contract: same call, not the next one (the desk sorts before
    # wf:contract: answering; phase-8 twin, asserted end to end here).
    pytest.fail("phase 9 pending")


def test_collect_merges_own_collectors_with_the_retired_pendings():
    # wf:contract: the response's datachanges merge the page's own captured
    # wf:contract: changes (its collector and its user_view, still local) with
    # wf:contract: the datachanges retired from the commander, ordered by
    # wf:contract: change_ts; dbevents stay their own species, never mixed.
    pytest.fail("phase 9 pending")


# ----------------------------------------------------------------------
# Addressed writes: one road, through the desk
# ----------------------------------------------------------------------


def test_set_datachange_to_any_target_travels_through_the_commander():
    # wf:contract: set_datachange keeps its full pre_refactoring signature
    # wf:contract: (identity, change, kind=, target=, filters=, replace=) and
    # wf:contract: ALWAYS routes through the desk — the own page included: no
    # wf:contract: local shortcut exists, the exchange happens anyway.
    pytest.fail("phase 9 pending")


def test_a_user_store_write_is_applied_before_the_collect_of_the_retriever():
    # wf:contract: STATE writes retired by the exchange are applied to the
    # wf:contract: user's own store Bag first (apply_forwarded, _original_ts
    # wf:contract: stamped), THEN the collect runs: the retrieving page reads
    # wf:contract: the captured change in the same response, and the sibling
    # wf:contract: pages — every connection, one shared Bag — capture it on
    # wf:contract: their own user_view for their own next drain.
    pytest.fail("phase 9 pending")


def test_the_dead_helpers_are_gone():
    # wf:contract: deposit_dbevent, fan_out_local and the worker's local
    # wf:contract: subscription index no longer exist on SpaWorker, and the
    # wf:contract: page item carries no dbevents mailbox — events never touch
    # wf:contract: the registry.
    pytest.fail("phase 9 pending")
