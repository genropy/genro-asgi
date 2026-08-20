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

"""Phase 5 contract: the site writes the global store, the write climbs the envelope.

Derived from ``tests/test_spa_global_store.py`` for the verb forms, REWRITTEN on
the ratified mechanics of 2026-08-20 (handoff §4.2 point 10), which the
pre_refactoring lock protocol does NOT describe:

- the ``WorkerConnector`` asymmetry stays intact — down CALL, up presentation
  and REPLY, nothing else; NO child-to-parent CALL/EVENT lane is opened;
- the worker applies a write to its OWN replica first (divergence from the
  pre_refactoring, where the author's replica waited for the push);
- the write rides the slot of the first useful envelope out, beside
  ``worker_snapshot`` (``_outbound``); on the other side ``_take_envelope``
  hands the whole envelope to the fold BEFORE unblocking the caller;
- the master redescends as it already does: every inbound envelope carries the
  whole global store (``_take_global_store``);
- ``old_value`` rides ONLY the derived writes (the ``global_store_lock`` case);
  a stale derived write is refused with a log line on the commander, no channel
  back to the site (risk accepted by the owner);
- absolute writes (``store_set`` / ``store_del`` outside the lock) stay
  last-writer-wins.

The executable half pins the worker-local surface, fixed by imitation. The
skeletons state the two-sided behaviour whose bindings (the envelope slot key,
the commander-side fold hook) the phase itself settles.
"""

from __future__ import annotations

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker

WORKER_NAME = "standard_0001"


@pytest.fixture
def worker(tmp_path):
    deposit = FreezeHandler(tmp_path / "frozen_users")
    return SpaWorker(WORKER_NAME, freeze_handler=deposit, deposit_lock_retry_interval=0.01)


# ----------------------------------------------------------------------
# The verbs, in the site's forms — and the replica written FIRST
# ----------------------------------------------------------------------


def test_store_set_answers_the_path_and_writes_the_own_replica_first(worker):
    answer = worker.store_set("alice", "gnr.a", value=1)

    assert answer == {"path": "gnr.a"}
    assert worker.global_store["gnr.a"] == 1


def test_store_del_removes_the_node_rather_than_nulling_it(worker):
    worker.store_set("alice", "gnr.a", value=1)

    answer = worker.store_del("alice", "gnr.a")

    assert answer == {"path": "gnr.a"}
    assert worker.global_store["gnr.a"] is None
    assert "a" not in worker.global_store["gnr"].keys()


def test_the_lock_yields_a_copy_that_reads_the_replica(worker):
    worker.store_set("alice", "gnr.a", value=12)

    with worker.global_store_lock() as copy:
        assert copy["gnr.a"] == 12
        copy.set_item("gnr.a", 24)

    assert worker.global_store["gnr.a"] == 24


def test_a_body_that_raises_applies_nothing(worker):
    """All-or-nothing: an interrupted lock writes nothing, locally either."""
    worker.store_set("alice", "gnr.a", value=1)

    with pytest.raises(RuntimeError, match="halfway"):
        with worker.global_store_lock() as copy:
            copy.set_item("gnr.a", 99)
            raise RuntimeError("halfway")

    assert worker.global_store["gnr.a"] == 1


# ----------------------------------------------------------------------
# The climb and the fold — bindings settled by the phase, behaviour fixed here
# ----------------------------------------------------------------------


def test_the_write_rides_the_first_envelope_out_beside_the_snapshot():
    # wf:contract: a store_set queues its write for the envelope slot that
    # wf:contract: _outbound composes, beside worker_snapshot; the next
    # wf:contract: envelope out carries it and the queue empties — no
    # wf:contract: child-to-parent CALL/EVENT lane is opened for it.
    pytest.fail("phase 5 pending")


def test_the_master_folds_the_writes_before_the_caller_is_unblocked():
    # wf:contract: on the commander side _take_envelope hands the envelope to
    # wf:contract: the fold BEFORE unblocking the caller; an absolute write in
    # wf:contract: it lands on the commander's global master (last writer
    # wf:contract: wins), and the master then redescends on the ordinary
    # wf:contract: GLOBAL_STORE_KEY of every outbound envelope.
    pytest.fail("phase 5 pending")


def test_a_derived_write_carries_old_value_and_a_stale_one_is_refused():
    # wf:contract: a write drained from a global_store_lock body carries the
    # wf:contract: old value it was derived from; the fold applies it only if
    # wf:contract: the master still holds that value, otherwise it refuses it
    # wf:contract: whole with one log line on the commander — no error channel
    # wf:contract: back to the site, and the master stays as it was.
    pytest.fail("phase 5 pending")


def test_an_absolute_write_never_carries_old_value():
    # wf:contract: store_set / store_del outside the lock travel WITHOUT the
    # wf:contract: old value and are never refused: last-writer-wins, the
    # wf:contract: commander a blind courier as today.
    pytest.fail("phase 5 pending")


def test_the_descending_store_still_replaces_the_replica_whole():
    # wf:contract: an inbound envelope carrying GLOBAL_STORE_KEY replaces the
    # wf:contract: worker's replica whole (_take_global_store), and the replica
    # wf:contract: the site reads through store_set/global_store_lock is that
    # wf:contract: hydrated one — the descent of the master closes the loop.
    pytest.fail("phase 5 pending")
