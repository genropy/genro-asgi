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

"""Lifespan protocol tests (SPECIFICATION.md §4): startup in order, shutdown
in reverse, one app's error does not block the others.

The ASGI lifespan protocol is driven directly through ``BaseServer.__call__``
(no uvicorn needed): a canned ``receive()`` queue delivers ``startup`` then
``shutdown``, and the recording apps append to a shared event list from their
hooks so ordering and error isolation can be asserted.
"""

from __future__ import annotations

from genro_asgi_core import BaseApplication, BaseServer


class SyncRecordingApp(BaseApplication):
    """Test app recording sync ``on_startup``/``on_shutdown`` to a shared list.

    Constructor kwargs peeled here: ``name`` — identifies this app in the
    recorded events; ``events`` — the shared list; ``raise_on`` — an optional
    iterable of hook names on which this app raises instead of recording.
    """

    def __init__(self, **kwargs: object) -> None:
        self.name: str = kwargs.pop("name")
        self.events: list[str] = kwargs.pop("events")
        self.raise_on: frozenset[str] = frozenset(kwargs.pop("raise_on", ()))
        super().__init__(**kwargs)

    def on_startup(self) -> None:
        self._record_or_raise("on_startup")

    def on_shutdown(self) -> None:
        self._record_or_raise("on_shutdown")

    def _record_or_raise(self, hook: str) -> None:
        if hook in self.raise_on:
            raise RuntimeError(f"{self.name}.{hook} failed")
        self.events.append(f"{self.name}.{hook}")


class AsyncRecordingApp(SyncRecordingApp):
    """Same recording behaviour, as async hooks."""

    async def on_startup(self) -> None:
        self._record_or_raise("on_startup")

    async def on_shutdown(self) -> None:
        self._record_or_raise("on_shutdown")


async def drive_lifespan(
    server: BaseServer, messages: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Feed ``messages`` to ``server``'s lifespan scope; return what it sent."""
    queue = list(messages)
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return queue.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await server({"type": "lifespan"}, receive, send)
    return sent


def startup_then_shutdown() -> list[dict[str, object]]:
    """A canned message queue: one full startup/shutdown round-trip."""
    return [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]


class TestOrdering:
    async def test_startup_runs_primary_then_mounts_in_order(self) -> None:
        events: list[str] = []
        server = BaseServer(primary=SyncRecordingApp(name="primary", events=events))
        server.mount(SyncRecordingApp(name="api", mount_name="api", events=events))
        server.mount(SyncRecordingApp(name="admin", mount_name="admin", events=events))

        sent = await drive_lifespan(server, startup_then_shutdown())

        startup_events = [e for e in events if e.endswith("on_startup")]
        assert startup_events == ["primary.on_startup", "api.on_startup", "admin.on_startup"]
        assert {"type": "lifespan.startup.complete"} in sent

    async def test_shutdown_runs_in_reverse_order(self) -> None:
        events: list[str] = []
        server = BaseServer(primary=SyncRecordingApp(name="primary", events=events))
        server.mount(SyncRecordingApp(name="api", mount_name="api", events=events))
        server.mount(SyncRecordingApp(name="admin", mount_name="admin", events=events))

        sent = await drive_lifespan(server, startup_then_shutdown())

        shutdown_events = [e for e in events if e.endswith("on_shutdown")]
        assert shutdown_events == ["admin.on_shutdown", "api.on_shutdown", "primary.on_shutdown"]
        assert {"type": "lifespan.shutdown.complete"} in sent


class TestErrorIsolation:
    async def test_raising_sync_startup_hook_does_not_block_others(self) -> None:
        events: list[str] = []
        server = BaseServer(primary=SyncRecordingApp(name="primary", events=events))
        server.mount(
            SyncRecordingApp(name="api", mount_name="api", events=events, raise_on={"on_startup"})
        )
        server.mount(SyncRecordingApp(name="admin", mount_name="admin", events=events))

        sent = await drive_lifespan(server, startup_then_shutdown())

        startup_events = [e for e in events if e.endswith("on_startup")]
        assert startup_events == ["primary.on_startup", "admin.on_startup"]
        assert {"type": "lifespan.startup.complete"} in sent
        assert {"type": "lifespan.shutdown.complete"} in sent

    async def test_raising_async_shutdown_hook_does_not_block_others(self) -> None:
        events: list[str] = []
        server = BaseServer(primary=AsyncRecordingApp(name="primary", events=events))
        server.mount(
            AsyncRecordingApp(
                name="api", mount_name="api", events=events, raise_on={"on_shutdown"}
            )
        )
        server.mount(AsyncRecordingApp(name="admin", mount_name="admin", events=events))

        sent = await drive_lifespan(server, startup_then_shutdown())

        shutdown_events = [e for e in events if e.endswith("on_shutdown")]
        assert shutdown_events == ["admin.on_shutdown", "primary.on_shutdown"]
        assert {"type": "lifespan.startup.complete"} in sent
        assert {"type": "lifespan.shutdown.complete"} in sent
