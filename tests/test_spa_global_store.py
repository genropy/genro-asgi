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

"""The global store's own classes, tested bare.

The store lives ONLY on the commander — there are no replicas — and the
whole desk (store_set/store_del/store_get on the lane, the lock grant that
carries the true master state, the release that applies exactly what was
drained) is pinned end to end by the orchestration contract tests
(``tests/orchestration/test_contract_phase10_global_store_desk.py`` and
``test_orchestration_store_get.py``). What belongs here is the module
itself: a ``CapturingGlobalStore`` captures what changed, a ``GlobalStore``
applies a drained batch faithfully, a snapshot seed keeps the Bag identity.
"""

from __future__ import annotations

from genro_tytx import from_tytx

from genro_asgi.spa.global_store import CapturingGlobalStore, GlobalStore


def test_a_store_applies_a_drained_batch_without_the_forwarding_residue() -> None:
    """The global store has one writer, so there is no second instant to carry."""
    master = CapturingGlobalStore()
    master.set("gnr.a", 1)
    master.bag.set_item("gnr.b", 2, _attributes={"tag": "x"})

    applied = GlobalStore()
    applied.apply_changes(master.drain())

    assert applied.bag["gnr.a"] == 1
    assert applied.bag["gnr.b"] == 2
    assert applied.bag.get_attr("gnr.b") == {"tag": "x"}
    assert "_original_ts" not in applied.bag.get_attr("gnr.b")


def test_a_delete_removes_the_node_rather_than_nulling_it() -> None:
    master = CapturingGlobalStore()
    master.set("gnr.a", 1)
    applied = GlobalStore()
    applied.apply_changes(master.drain())

    master.delete("gnr.a")
    applied.apply_changes(master.drain())

    assert applied.bag["gnr.a"] is None
    assert "a" not in applied.bag["gnr"].keys()


def test_a_snapshot_round_trip_keeps_the_bag_identity() -> None:
    """``load_snapshot`` refills the Bag in place, so a seed must not swap it."""
    master = CapturingGlobalStore()
    master.set("gnr.a", 1)
    store = GlobalStore()
    held = store.bag
    store.bag.set_item("stale", "gone")

    store.load_snapshot(master.snapshot())

    assert store.bag is held
    assert held["gnr.a"] == 1
    assert "stale" not in held.keys()


def test_a_working_copy_captures_nothing_of_its_own_hydration() -> None:
    """The grant's order, here too: hydrate the Bag first, attach the collector after."""
    master = CapturingGlobalStore()
    master.set("gnr.a", 1)
    master.drain()
    hydrated = from_tytx(master.snapshot(), "json")

    copy = CapturingGlobalStore(hydrated)

    assert copy.bag["gnr.a"] == 1
    assert copy.drain() == []
    copy.bag.set_item("gnr.b", 2)
    assert [change["key"]["path"] for change in copy.drain()] == ["gnr.b"]
