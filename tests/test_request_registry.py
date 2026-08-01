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

"""Request-registry tests (SPECIFICATION.md §4): two concurrent requests each
see their OWN request via the instance-owned ContextVar (the ContextVar test);
``in_flight`` counts both at a rendezvous and returns to zero afterwards;
``snapshot()`` exposes the slotted record fields; registration is cleaned up
even when the handler raises.

Driven at the ASGI level (no uvicorn): two concurrent tasks call the server and
an ``asyncio.Barrier`` holds both in-flight so the picture is observed
simultaneously — deterministic, and it mirrors the other Phase 0 tests.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from genro_asgi import BaseApplication, BaseServer
from genro_asgi.request_registry import RegisteredRequest
from genro_asgi.types import Receive, Scope, Send


class RendezvousApp(BaseApplication):
    """Primary app recording the registry picture while blocked at a barrier.

    Constructor kwargs peeled here (cooperative chain): ``barrier`` (shared by
    both requests) and ``observed`` (a dict the app writes its picture into).
    """

    def __init__(self, **kwargs: Any) -> None:
        self.barrier: asyncio.Barrier = kwargs.pop("barrier")
        self.observed: dict[int, dict[str, Any]] = kwargs.pop("observed")
        super().__init__(**kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        registry = self.server.requests
        own = registry.current
        assert own is not None  # inside a request the ContextVar is always set
        await self.barrier.wait()  # both requests are registered past this point
        self.observed[own.request_id] = {
            "current_is_own": registry.current is own,
            "in_flight": registry.in_flight,
            "snapshot": registry.snapshot(),
            "path": own.path,
            "scope_type": own.scope_type,
        }
        await self.barrier.wait()  # hold both here so neither unregisters early
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


class RaisingApp(BaseApplication):
    """Primary app that always raises — to test cleanup on the error path."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError("boom")


class CleanupThenRaiseApp(BaseApplication):
    """Registers a request cleanup on ``current`` and then raises.

    Constructor kwarg peeled here: ``ran`` — a list the cleanup appends to, so
    the test can assert the cleanup ran despite the handler raising.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.ran: list[str] = kwargs.pop("ran")
        super().__init__(**kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        current = self.server.requests.current
        assert current is not None
        current.add_cleanup(lambda: self.ran.append("cleanup"))
        raise RuntimeError("boom")


async def drive(server: BaseServer, path: str) -> None:
    """Drive one http request through the server at the ASGI level."""

    async def receive() -> dict[str, object]:
        return {"type": "http.request"}

    async def send(message: dict[str, object]) -> None:
        pass

    await server({"type": "http", "path": path}, receive, send)


class TestRegisteredRequest:
    def test_record_is_slotted_and_exposes_its_fields(self) -> None:
        item = RegisteredRequest(1, "http", "/x")
        assert item.request_id == 1
        assert item.scope_type == "http"
        assert item.path == "/x"
        assert isinstance(item.started_at, float)
        assert not hasattr(item, "__dict__")  # D18: slotted, no per-instance dict


class TestEmptyRegistry:
    def test_fresh_registry_is_empty(self) -> None:
        server = BaseServer(applications=[BaseApplication(mount="")])
        assert server.requests.current is None
        assert server.requests.in_flight == 0
        assert server.requests.snapshot() == []


class TestConcurrentRequests:
    async def test_each_request_sees_its_own_current_and_in_flight_counts_both(
        self,
    ) -> None:
        barrier = asyncio.Barrier(2)
        observed: dict[int, dict[str, Any]] = {}
        server = BaseServer(applications=[RendezvousApp(mount="", barrier=barrier, observed=observed)])

        await asyncio.gather(drive(server, "/a"), drive(server, "/b"))

        assert len(observed) == 2
        for picture in observed.values():
            assert picture["current_is_own"] is True  # the ContextVar test
            assert picture["in_flight"] == 2
        # monotonic ids: two distinct requests numbered 1 and 2
        assert set(observed) == {1, 2}
        # the two requests carry the two distinct paths
        assert {p["path"] for p in observed.values()} == {"/a", "/b"}

    async def test_snapshot_lists_the_in_flight_records(self) -> None:
        barrier = asyncio.Barrier(2)
        observed: dict[int, dict[str, Any]] = {}
        server = BaseServer(applications=[RendezvousApp(mount="", barrier=barrier, observed=observed)])

        await asyncio.gather(drive(server, "/a"), drive(server, "/b"))

        snapshot = next(iter(observed.values()))["snapshot"]
        assert len(snapshot) == 2
        assert all(isinstance(r, RegisteredRequest) for r in snapshot)
        assert all(r.scope_type == "http" for r in snapshot)
        assert {r.path for r in snapshot} == {"/a", "/b"}

    async def test_registry_is_empty_after_both_complete(self) -> None:
        barrier = asyncio.Barrier(2)
        observed: dict[int, dict[str, Any]] = {}
        server = BaseServer(applications=[RendezvousApp(mount="", barrier=barrier, observed=observed)])

        await asyncio.gather(drive(server, "/a"), drive(server, "/b"))

        assert server.requests.in_flight == 0
        assert server.requests.snapshot() == []
        assert server.requests.current is None


class TestErrorPath:
    async def test_request_is_unregistered_even_when_handler_raises(self) -> None:
        server = BaseServer(applications=[RaisingApp(mount="")])
        with pytest.raises(RuntimeError, match="boom"):
            await drive(server, "/boom")
        assert server.requests.in_flight == 0
        assert server.requests.current is None

    async def test_cleanups_drained_even_when_handler_raises(self) -> None:
        ran: list[str] = []
        server = BaseServer(applications=[CleanupThenRaiseApp(mount="", ran=ran)])
        with pytest.raises(RuntimeError, match="boom"):
            await drive(server, "/boom")
        assert ran == ["cleanup"]  # the finally drained the cleanup despite the raise
        assert server.requests.in_flight == 0


class TestCleanups:
    def test_add_cleanup_runs_lifo(self) -> None:
        item = RegisteredRequest(1, "http", "/")
        order: list[str] = []
        item.add_cleanup(lambda: order.append("a"))
        item.add_cleanup(lambda: order.append("b"))
        item.run_cleanups()
        assert order == ["b", "a"]  # last registered runs first

    def test_exception_in_one_cleanup_does_not_stop_the_rest(self) -> None:
        item = RegisteredRequest(1, "http", "/")
        order: list[str] = []

        def boom() -> None:
            raise RuntimeError("cleanup failure")

        item.add_cleanup(lambda: order.append("first"))
        item.add_cleanup(boom)
        item.add_cleanup(lambda: order.append("last"))
        item.run_cleanups()
        assert order == ["last", "first"]  # LIFO; the raising one is isolated

    def test_exception_in_a_cleanup_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        item = RegisteredRequest(1, "http", "/")

        def boom() -> None:
            raise RuntimeError("cleanup failure")

        item.add_cleanup(boom)
        with caplog.at_level("ERROR", logger="genro_asgi.request_registry"):
            item.run_cleanups()
        assert any(
            "Request cleanup" in record.message and record.exc_info
            for record in caplog.records
        )

    def test_run_cleanups_is_noop_without_any(self) -> None:
        item = RegisteredRequest(1, "http", "/")
        item.run_cleanups()  # no cleanups queued → nothing happens, no error
