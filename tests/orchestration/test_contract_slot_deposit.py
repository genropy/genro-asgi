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

"""Every request delivers what its slot still holds before it returns.

A commit's deposits used to leave the worker only inside ``collect_page``, which
only a page's own envelope reaches: a ``rootPage`` webhook, or a request that
failed after its commit, announced to nobody. The end of the stitching now
delivers whatever the slot still holds through ``/desk/deposit`` — filed in the
subscribers' queues, nothing retired, because there is no page to answer — and
after a collect the slot is empty, so nothing is delivered twice.
"""

from __future__ import annotations

import pytest

from genro_asgi.spa.environ import WsgiSeam
from genro_asgi.spa.orchestration.worker_connector import CommanderCallFailed

from .conftest import wait_for

TABLE = "customer"


@pytest.fixture
async def two_lanes(desk_lane, second_desk_lane):
    """The two lanes with one page each, ``p2`` subscribing the table."""
    desk_lane.worker.add_connection("c1", sticky_cid="spa-c1")
    desk_lane.worker.add_page("p1", "c1")
    second_desk_lane.worker.add_connection("c2", sticky_cid="spa-c2")
    second_desk_lane.worker.add_page("p2", "c2")
    await second_desk_lane.verb("subscribeTable", "alice", table=TABLE, page_id="p2")
    await wait_for(lambda: desk_lane.worker.subscribed_tables == {TABLE})
    return desk_lane, second_desk_lane


async def test_a_request_that_never_collected_delivers_its_deposits(two_lanes):
    # wf:contract: a commit with no collect behind it reaches the subscriber
    # wf:contract: anyway: the end of the request delivers the slot itself.
    lane, other = two_lanes
    await lane.open_request()
    await lane.verb("notifyDbEvents", "alice", dbevents={TABLE: ["ins:1"]}, page_id="p1")

    await lane.verb("deliver_slot_deposits")

    delivery = await other.verb("collect_page", "p2")
    assert [deposit["table"] for deposit in delivery["dbevents"]] == [TABLE]
    assert delivery["dbevents"][0]["from_page_id"] == "p1"


async def test_a_collected_request_delivers_its_deposits_once(two_lanes):
    # wf:contract: the collect empties the slot, so the end-of-request delivery
    # wf:contract: finds nothing: the subscriber holds exactly one deposit.
    lane, other = two_lanes
    await lane.open_request()
    await lane.verb("notifyDbEvents", "alice", dbevents={TABLE: ["ins:1"]}, page_id="p1")
    await lane.verb("collect_page", "p1")

    await lane.verb("deliver_slot_deposits")

    assert len(lane.desk.page_dbevent_map["p2"]) == 1


async def test_an_empty_slot_places_no_call(two_lanes, monkeypatch):
    # wf:contract: a table nobody subscribes is filtered at the source, so the
    # wf:contract: end-of-request delivery has nothing to send and sends nothing.
    lane, _other = two_lanes
    await lane.open_request()
    await lane.verb("notifyDbEvents", "alice", dbevents={"orders": ["ins:1"]}, page_id="p1")

    calls = []
    monkeypatch.setattr(lane.worker, "call", lambda *args, **kwargs: calls.append(args))
    await lane.verb("deliver_slot_deposits")

    assert calls == []


async def test_a_request_failing_after_its_commit_still_delivers(two_lanes):
    # wf:contract: the delivery sits in the ``finally`` of the stitching: the
    # wf:contract: exception propagates, and the deposits are filed all the same.
    lane, other = two_lanes

    def wsgi_app(environ, start_response):
        lane.worker.notifyDbEvents("alice", dbevents={TABLE: ["ins:1"]}, page_id="p1")
        raise RuntimeError("the site failed after its commit")

    seam = WsgiSeam(wsgi_app)
    payload = {"http": {"method": "GET", "path": "/", "cid": "c1"}, "identity": "alice"}

    with pytest.raises(RuntimeError):
        await lane.verb("_serve_on_thread", seam, payload)

    assert [deposit["table"] for deposit in lane.desk.page_dbevent_map["p2"]] == [TABLE]


async def test_a_refused_deposit_never_replaces_the_sites_own_exception(two_lanes, monkeypatch):
    # wf:contract: the delivery in the ``finally`` logs a refusal and drops the
    # wf:contract: deposits; the site's exception is what propagates, never the
    # wf:contract: transport's.
    lane, other = two_lanes

    async def refusing_call(path, data=None):
        raise CommanderCallFailed(path, "refused for the test")

    monkeypatch.setattr(lane.worker, "call", refusing_call)

    def wsgi_app(environ, start_response):
        lane.worker.notifyDbEvents("alice", dbevents={TABLE: ["ins:1"]}, page_id="p1")
        raise RuntimeError("the site failed after its commit")

    seam = WsgiSeam(wsgi_app)
    payload = {"http": {"method": "GET", "path": "/", "cid": "c1"}, "identity": "alice"}

    with pytest.raises(RuntimeError):
        await lane.verb("_serve_on_thread", seam, payload)

    assert "p2" not in lane.desk.page_dbevent_map
