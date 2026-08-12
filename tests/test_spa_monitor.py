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

"""The monitor observables: the worker's ``monitor_state``, the commander's view.

``metrics_view`` is the evaluator read scaled for bars; ``population`` is the
fan-out of ``monitor_state`` over the channel, with the commander's own per-user
consumption fused into the user rows. The fan-out is exercised for real in
single mode — one commander, its own worker, the whole CALL round trip — and its
failure leg against a roster row whose worker answers nothing.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from genro_asgi.channel.hub import ChannelCallError
from genro_asgi.spa.commander import UserStickyCommander
from genro_asgi.spa.worker import UserStickyWorker


@pytest.fixture
async def single() -> Any:
    """A commander in the single role: no child, its own worker, no heartbeat."""
    commander = UserStickyCommander(workers=0, local_worker=True)
    await commander.start()
    try:
        yield commander
    finally:
        await commander.stop()


@pytest.fixture
def commander(tmp_path: Any) -> UserStickyCommander:
    """A commander with one enrolled worker and a hub that is never started."""
    running = UserStickyCommander(workers=0, path=str(tmp_path / "hub.sock"))
    running.worker_roster["W:w-1"] = running.new_roster_row(0, None)
    running.worker_roster["W:w-1"]["status"] = "active"
    return running


def report(
    cpu: float | None = None,
    rss: int | None = None,
    busy: int = 0,
    total: int = 0,
    reusable: int | None = None,
) -> dict[str, Any]:
    """A raw occupancy reading with only the fields the formula reads set."""
    return {
        "cpu": cpu,
        "rss": rss,
        "reusable": reusable,
        "executor": {"busy": busy, "total": total},
    }


def explode(running: UserStickyCommander) -> None:
    """Make every ``hub.call`` of this commander raise before answering."""

    async def call(worker: str, path: str, data: Any, timeout: Any = None) -> dict[str, Any]:
        raise ChannelCallError(worker, path, {"message": "boom"})

    running.hub.call = call  # type: ignore[method-assign]


# ----------------------------------------------------------------------
# The worker's side: the three registers, wire-safe
# ----------------------------------------------------------------------


async def test_monitor_state_answers_one_row_per_register_entry() -> None:
    worker = UserStickyWorker("W:w1")
    worker.registry.new_connection("c1", user="alice")
    worker.registry.new_page("p1", user="alice", session_id="s1", connection_id="c1")
    state = await worker.monitor_state()
    assert state["worker"] == "W:w1"
    assert [row["register_item_id"] for row in state["users"]] == ["alice"]
    assert [row["register_item_id"] for row in state["connections"]] == ["c1"]
    assert [row["register_item_id"] for row in state["pages"]] == ["p1"]


async def test_monitor_state_projects_scalars_never_the_working_fields() -> None:
    """A store, the page ``data``, a pending dbevent or a subscription set is
    worker memory (or application content), not an observable: the photo
    carries identity, ancestry, clocks and counts — and is JSON-clean."""
    worker = UserStickyWorker("W:w1")
    worker.registry.new_connection("c1", user="alice")
    worker.registry.new_page(
        "p1", user="alice", session_id="s1", connection_id="c1", data={"secret": "x"}
    )
    worker.page_items.get("p1")["dbevents"].append({"table": "sys.user", "batch": [{"id": 1}]})
    state = await worker.monitor_state()
    page = state["pages"][0]
    working = {"store", "collector", "user_view", "data", "dbevents", "subscribed_paths"}
    assert not working & set(page)
    assert page["connection_id"] == "c1" and page["root_page_id"] == "p1"
    user = state["users"][0]
    assert user["connections"] == 1 and user["pages"] == 1
    assert state["connections"][0]["pages"] == 1
    json.dumps(state)


async def test_monitor_state_ages_the_clocks_at_photo_time() -> None:
    """``age_s`` comes from the same clock that wrote the stamp; the two
    client-reported clocks are None until the page protocol carries them."""
    worker = UserStickyWorker("W:w1")
    worker.registry.new_connection("c1", user="alice")
    row = (await worker.monitor_state())["users"][0]
    assert row["last_refresh_ts"] > 0
    assert row["age_s"] >= 0.0
    assert row["last_user_ts"] is None and row["last_rpc_ts"] is None


async def test_monitor_state_skips_a_row_swept_mid_photo(monkeypatch: Any) -> None:
    """The lock-free photo of a moving subject: a key listed, then swept before
    its read (the race a concurrent sync op produces) yields no row, no crash,
    and the neighbours stay in the picture."""
    worker = UserStickyWorker("W:w1")
    worker.registry.new_connection("c1", user="alice")
    worker.registry.new_connection("c2", user="bob")
    original = worker.connection_items.get
    monkeypatch.setattr(
        worker.connection_items, "get", lambda key: None if key == "c1" else original(key)
    )
    state = await worker.monitor_state()
    assert [row["register_item_id"] for row in state["connections"]] == ["c2"]
    # alice is still in the photo; her count just cannot reach through the
    # swept edge, exactly as if the walk had started a beat later
    assert [row["register_item_id"] for row in state["users"]] == ["alice", "bob"]


async def test_monitor_state_of_an_empty_worker_is_three_empty_lists() -> None:
    worker = UserStickyWorker("W:w1")
    assert await worker.monitor_state() == {
        "worker": "W:w1",
        "users": [],
        "connections": [],
        "pages": [],
    }


# ----------------------------------------------------------------------
# metrics_view: the evaluator read, scaled 0-100
# ----------------------------------------------------------------------


def test_metrics_view_scales_the_evaluator_read_for_the_bars(
    commander: UserStickyCommander,
) -> None:
    commander.record_occupancy("W:w-1", report(cpu=0.4, busy=1, total=4))
    commander.count_forward("W:w-1", 0.5)
    view = commander.metrics_view()
    assert set(view) == {"W:w-1"}
    # occupancy is the SATURATION: the max ratio against the 0.8 admission
    # target (cpu 0.4 / 0.8 = 0.5), while the components stay raw fractions
    assert view["W:w-1"]["occupancy"] == 50
    assert view["W:w-1"]["components"] == {"cpu": 40, "executor": 25}
    # the history is the per-row SATURATION, on the bar's own axis
    assert view["W:w-1"]["history"] == [50]
    assert view["W:w-1"]["forward"] == {"requests": 1, "errors": 0, "seconds": 0.5}


def test_metrics_view_memory_bar_reads_live_memory(
    commander: UserStickyCommander,
) -> None:
    """The bar judges rss minus the reusable heap against the configured limit."""
    commander.memory_limit_mb = 100
    commander.record_occupancy(
        "W:w-1", report(rss=80 * 1024 * 1024, reusable=30 * 1024 * 1024)
    )
    assert commander.metrics_view()["W:w-1"]["components"]["memory"] == 50


def test_metrics_view_hands_out_a_copy_of_the_counters(
    commander: UserStickyCommander,
) -> None:
    """Like the archived snapshot: the view is the consumer's to annotate."""
    commander.count_forward("W:w-1", 0.5)
    view = commander.metrics_view()
    view["W:w-1"]["forward"]["requests"] = 999
    assert commander.forward_counters["W:w-1"]["requests"] == 1


def test_metrics_view_gives_a_worker_that_never_forwarded_the_zero_counters(
    commander: UserStickyCommander,
) -> None:
    commander.record_occupancy("W:w-1", report(busy=2, total=4))
    view = commander.metrics_view()
    assert view["W:w-1"]["forward"] == {"requests": 0, "errors": 0, "seconds": 0.0}
    # A single row cannot carry a rate: there is no interval to divide by.
    assert view["W:w-1"]["rates"] == {"rps": None, "latency_ms": None}


def test_metrics_view_carries_the_rates_once_the_window_holds_two_rows(
    commander: UserStickyCommander,
) -> None:
    commander.record_occupancy("W:w-1", report(busy=1, total=4))
    commander.count_forward("W:w-1", 0.5)
    commander.record_occupancy("W:w-1", report(busy=2, total=4))
    rates = commander.metrics_view()["W:w-1"]["rates"]
    assert rates is not None
    assert rates["latency_ms"] == pytest.approx(500.0)


def test_metrics_view_ignores_a_worker_that_is_not_active(
    commander: UserStickyCommander,
) -> None:
    commander.record_occupancy("W:w-1", report(busy=2, total=4))
    commander.worker_roster["W:w-1"]["status"] = "gone"
    assert commander.metrics_view() == {}


def test_metrics_view_carries_the_last_floor_and_rounded_time_to_limit(
    commander: UserStickyCommander,
) -> None:
    commander.memory_limit_mb = 200
    commander.record_occupancy("W:w-1", report(busy=1, total=4))
    now = time.time()
    commander.worker_roster["W:w-1"]["floors"].extend(
        [
            {"ts": now - index * 3600, "floor": (99.96 - index) * 1024 * 1024}
            for index in range(6, -1, -1)
        ]
    )
    view = commander.metrics_view()["W:w-1"]
    assert view["floor"] == pytest.approx(99.96 * 1024 * 1024)
    # The raw T is 100.04 hours: only an actual one-decimal rounding gives 100.0,
    # so dropping the round (or widening it) fails here.
    assert view["time_to_limit"] == 100.0


def test_metrics_view_gives_none_floor_and_time_to_limit_with_no_series(
    commander: UserStickyCommander,
) -> None:
    commander.record_occupancy("W:w-1", report(busy=1, total=4))
    view = commander.metrics_view()["W:w-1"]
    assert view["floor"] is None
    assert view["time_to_limit"] is None


# ----------------------------------------------------------------------
# population: the fan-out, and the consumption fused on arrival
# ----------------------------------------------------------------------


async def test_population_gathers_the_registers_of_the_live_worker(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_connection")
    await single.forward_call("sess-1", "/op/new_page", {"page_id": "p1", "session_id": "sess-1"})
    people = await single.population()
    assert len(people["workers"]) == 1
    row = people["workers"][0]
    assert row["id"] == single.worker.name
    assert row["group"] == single.group
    assert "error" not in row
    assert [user["register_item_id"] for user in row["users"]] == ["sess-1"]
    assert [page["register_item_id"] for page in row["pages"]] == ["p1"]
    assert len(row["connections"]) == 1


async def test_population_fuses_only_the_cumulative_consumption(
    single: UserStickyCommander,
) -> None:
    """The bucket ring is the rebalance's private window: it never crosses."""
    await single.forward_call("sess-1", "/op/new_connection")
    single.count_user_consumption("sess-1", 0.25)
    single.count_user_consumption("sess-1", 0.75)
    user_row = (await single.population())["workers"][0]["users"][0]
    assert user_row["consumption"] == {"requests": 2, "seconds": pytest.approx(1.0)}
    assert "buckets" not in user_row["consumption"]


async def test_population_leaves_an_unknown_user_row_without_consumption(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_connection")
    assert "consumption" not in (await single.population())["workers"][0]["users"][0]


async def test_population_degrades_a_silent_worker_to_an_error_row(
    commander: UserStickyCommander,
) -> None:
    """One worker gone is a row with an error, never an exception upward."""
    explode(commander)
    assert await commander.population() == {
        "workers": [{"id": "W:w-1", "group": commander.group, "error": "unreachable"}]
    }
