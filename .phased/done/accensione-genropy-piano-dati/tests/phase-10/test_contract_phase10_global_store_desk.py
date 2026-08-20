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

"""Phase 10 contract: the global store lives only on the commander.

The ratified digression (registro 2026-08-20 §7-bis): no replicas on the
workers — verified fact: the 22-name site contract never reads the global store
directly, it only touches it through ``store_set``, ``store_del`` and the copy
``global_store_lock`` grants. Every access is a CALL on the phase-7 lane, with
an immediate REPLY. The lock is the pre_refactoring protocol carried over: the
grant brings the master's copy, the release applies the drained changes —
full-shape (attributes, reason, fired), so nothing is lost on the way up.

Derived from ``tests/test_spa_global_store.py``, the original contract of that
protocol; what the envelope mechanics of the executed phase 5 added (replicas,
old_value, the writes slot) dies with this phase.
"""

from __future__ import annotations

import pytest


def test_store_set_lands_on_the_master_before_it_answers():
    # wf:contract: store_set(identity, path, value=) is a CALL on the lane;
    # wf:contract: when it returns {"path": path}, the commander's master
    # wf:contract: already holds the value — no replica anywhere, no waiting
    # wf:contract: for any later push.
    pytest.fail("phase 10 pending")


def test_store_del_removes_the_node_rather_than_nulling_it():
    # wf:contract: after store_del returns, the master's node is GONE — not
    # wf:contract: None — exactly the pre_refactoring delete semantics.
    pytest.fail("phase 10 pending")


def test_the_grant_carries_the_true_master_state():
    # wf:contract: global_store_lock's acquire answers with the master's own
    # wf:contract: copy at grant time — a worker that never saw any state reads
    # wf:contract: the current truth from the copy, no staleness question.
    pytest.fail("phase 10 pending")


def test_the_release_applies_exactly_what_was_drained_in_full_shape():
    # wf:contract: changes made on the granted copy land on the master only at
    # wf:contract: the release, attributes and reason included; while the lock
    # wf:contract: is held the master shows nothing of them.
    pytest.fail("phase 10 pending")


def test_a_body_that_raises_applies_nothing():
    # wf:contract: a lock body that raises releases with nothing applied — the
    # wf:contract: all-or-nothing of the pre_refactoring lease.
    pytest.fail("phase 10 pending")


def test_the_waiters_are_served_in_order_and_see_the_previous_release():
    # wf:contract: a second holder's grant is taken from the master AFTER the
    # wf:contract: first holder's release applied: FIFO, read-modify-write safe.
    pytest.fail("phase 10 pending")


def test_a_dead_holders_lock_is_released_with_the_master_untouched():
    # wf:contract: the holder's channel ending releases the lock without
    # wf:contract: applying its half-made changes; the next waiter gets a clean
    # wf:contract: grant — the pre_refactoring death rule, on the new lane.
    pytest.fail("phase 10 pending")


def test_the_replica_machinery_is_gone():
    # wf:contract: SpaWorker holds no global replica and no queued writes; no
    # wf:contract: envelope slot carries the global store in either direction;
    # wf:contract: old_value exists nowhere — the phase-5 envelope mechanics
    # wf:contract: are fully removed with their tests rewritten (foreman
    # wf:contract: decision, notes.md).
    pytest.fail("phase 10 pending")
