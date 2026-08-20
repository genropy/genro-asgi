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

"""Phase 7 contract: the worker-to-commander CALL lane.

The redesign's foundation (registro 2026-08-20 §1): ``WorkerConnector`` learns
the second dispatch branch — a CALL arriving FROM the child is served as a task
and answered with a REPLY — and the worker learns to place a call and await its
answer. The transport is already full duplex and frames carry ids: the
conversations interleave without confusion. The channel doctrine always had the
two sides («REPLY si risolve inline, CALL/EVENT si servono come task»); this
phase finishes the half the connector implemented.

Bindings (method names, the handler hook the commander exposes) are settled by
the phase: skeletons state the behaviour, the executable shape is the phase's
work. The `ENVELOPE_SLOT_*` renames ride this phase too — they touch the same
file.
"""

from __future__ import annotations

import pytest


def test_a_worker_call_is_served_and_answered_while_the_parents_call_is_still_open():
    # wf:contract: while the worker is serving a CALL the commander made (the
    # wf:contract: request is mid-flight), the worker places its own CALL on
    # wf:contract: the same wire; the connector serves it as a task, a handler
    # wf:contract: on the parent side answers, and the worker's awaited future
    # wf:contract: resolves with that REPLY — the parent's original CALL is
    # wf:contract: still pending throughout and completes normally afterwards.
    pytest.fail("phase 7 pending")


def test_two_worker_calls_interleave_by_frame_id():
    # wf:contract: two CALLs placed by the worker without awaiting the first
    # wf:contract: resolve each with its own REPLY, matched by frame id, in
    # wf:contract: whatever order the parent answers.
    pytest.fail("phase 7 pending")


def test_a_worker_call_from_a_pool_thread_reaches_the_loop_and_returns():
    # wf:contract: the request runs on a traffic-pool thread; the worker's
    # wf:contract: call() is reachable from that thread (hop onto the loop,
    # wf:contract: the pre_refactoring pattern of the global lock) and hands
    # wf:contract: the REPLY payload back to the calling thread.
    pytest.fail("phase 7 pending")


def test_a_call_the_parent_has_no_handler_for_answers_an_error_not_silence():
    # wf:contract: a CALL path the commander does not serve comes back as an
    # wf:contract: error REPLY the worker can raise on — never a dropped frame
    # wf:contract: and never a warning-and-discard.
    pytest.fail("phase 7 pending")


def test_the_envelope_slot_constants_wear_the_family_prefix():
    # wf:contract: the surviving envelope slot constants are named
    # wf:contract: ENVELOPE_SLOT_WORKER_EVENTS, ENVELOPE_SLOT_WORKER_SNAPSHOT,
    # wf:contract: ENVELOPE_SLOT_PRESENTATION, live in worker_connector.py,
    # wf:contract: keep their wire values ("worker_events", "worker_snapshot",
    # wf:contract: "pid"), and no bare string literal writes those slots any
    # wf:contract: more (the two M2/M3 stray literals are gone).
    pytest.fail("phase 7 pending")
