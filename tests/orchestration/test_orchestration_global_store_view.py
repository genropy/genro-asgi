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

"""The published global store: one writer, versioned reads, no round trip."""

from __future__ import annotations

import struct

import pytest
from genro_bag import Bag

from genro_asgi.spa.orchestration import (
    FreezeHandler,
    GlobalStorePublisher,
    GlobalStoreView,
    GroupHandler,
    SpaCommander,
    SpaWorker,
)
from genro_asgi.spa.orchestration.global_store_view import GROWTH_STEP, HEADER
from genro_asgi.spa.orchestration.worker_handler import WorkerHandler


@pytest.fixture
def map_path(tmp_path):
    return tmp_path / "global_store.map"


def test_a_published_store_is_read_back_whole(map_path):
    publisher = GlobalStorePublisher(map_path)
    store = Bag()
    store["CACHE_TS.adm_htag"] = "2026-08-20"
    publisher.publish(store)

    view = GlobalStoreView(map_path)
    assert view.store["CACHE_TS.adm_htag"] == "2026-08-20"


def test_an_unchanged_version_answers_from_the_cache(map_path):
    publisher = GlobalStorePublisher(map_path)
    store = Bag()
    store["x"] = 1
    publisher.publish(store)

    view = GlobalStoreView(map_path)
    first = view.store
    assert view.store is first  # same version, same decoded Bag

    store["x"] = 2
    publisher.publish(store)
    fresh = view.store
    assert fresh is not first
    assert fresh["x"] == 2


def test_the_readers_copy_is_its_own(map_path):
    """Writing the view's Bag changes nothing published: writes go on the lane."""
    publisher = GlobalStorePublisher(map_path)
    store = Bag()
    store["x"] = 1
    publisher.publish(store)

    view = GlobalStoreView(map_path)
    view.store["x"] = 99

    assert GlobalStoreView(map_path).store["x"] == 1


def test_the_file_grows_past_its_first_step_and_is_still_readable(map_path):
    publisher = GlobalStorePublisher(map_path)
    view = GlobalStoreView(map_path)
    assert view.store.keys() == []  # the empty first publish, mapped small

    store = Bag()
    store["big.blob"] = "x" * (2 * GROWTH_STEP)
    publisher.publish(store)

    assert GlobalStoreView(map_path).store["big.blob"] == "x" * (2 * GROWTH_STEP)
    assert view.store["big.blob"] == "x" * (2 * GROWTH_STEP)  # the old view remaps


def test_a_read_that_stays_torn_errors_out_loud(map_path):
    publisher = GlobalStorePublisher(map_path)
    publisher.publish(Bag())
    # A write frozen in flight: seq forced ODD by hand, never completed.
    with open(map_path, "r+b") as f:
        f.write(struct.pack("<QQ", 7, 0))
    view = GlobalStoreView(map_path)

    with pytest.raises(RuntimeError, match="torn"):
        view.store
    assert HEADER.size == 16  # the layout the hand-forged header assumed


def test_the_desk_writes_are_published(tmp_path, map_path):
    commander = SpaCommander(tmp_path / "frozen_users", global_store_path=map_path)
    view = GlobalStoreView(map_path)

    commander.delivery_desk.op_store_set("CACHE_TS.x", "t1")
    assert view.store["CACHE_TS.x"] == "t1"

    commander.delivery_desk.op_store_del("CACHE_TS.x")
    assert view.store["CACHE_TS.x"] is None


def test_the_worker_reads_locally_and_refuses_when_unconfigured(tmp_path, map_path):
    publisher = GlobalStorePublisher(map_path)
    store = Bag()
    store["x"] = 1
    publisher.publish(store)

    deposit = FreezeHandler(tmp_path / "frozen_users")
    reader = SpaWorker("standard_0001", freeze_handler=deposit, global_store_path=str(map_path))
    assert reader.global_store["x"] == 1

    blind = SpaWorker("standard_0002", freeze_handler=deposit)
    with pytest.raises(RuntimeError, match="global_store_path"):
        blind.global_store


def test_the_path_travels_in_the_spawn_payload(tmp_path, map_path):
    commander = SpaCommander(tmp_path / "frozen_users", global_store_path=map_path)
    group = GroupHandler(
        commander,
        "standard",
        memory_concession_bytes=8 * 1024 * 1024 * 1024,
        instance_dir=tmp_path / "i",
        frozen_users_path=tmp_path / "frozen_users",
        entry_module="never.launched",
        global_store_path=map_path,
    )
    handler = WorkerHandler(group, "standard_0001", **group.worker_settings)
    assert handler.spawn_payload["global_store_path"] == str(map_path)
