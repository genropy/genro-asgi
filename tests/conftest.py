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

"""Shared ASGI-level test helpers, promoted from ``test_middleware_std.py``.

Every helper is a fixture returning a callable, so any test file can drive a
request through a composed server's ``__call__`` and read the recorded
messages without re-declaring the boilerplate: ``http_request`` runs one
request and returns the ``send`` messages; ``response_status`` /
``response_headers`` / ``response_body`` read that message list.

``genro_asgi_home`` is autouse: no test ever reads the developer's real
``~/.genroasgi``, whose ``config.py`` would otherwise layer itself under every
``AsgiServer(config=...)`` built here.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Callable

import pytest

from genro_asgi.config import HOME_ENV
from genro_asgi.types import Message, Scope


@pytest.fixture(autouse=True)
def genro_asgi_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Autouse: point ``GENRO_ASGI_HOME`` at an empty per-test directory.

    A test that WANTS a defaults recipe writes its own ``config.py`` in the
    returned directory; every other test gets a home with nothing in it.
    """
    home = tmp_path / "genroasgi_home"
    home.mkdir()
    monkeypatch.setenv(HOME_ENV, str(home))
    return home


@pytest.fixture
def http_request() -> Callable[..., object]:
    """Fixture: drive one request through a server at the ASGI level."""

    async def _http_request(
        server: object,
        path: str = "/",
        method: str = "GET",
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> list[Message]:
        scope: Scope = {"type": "http", "method": method, "path": path, "headers": headers or []}
        sent: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request"}

        async def send(message: Message) -> None:
            sent.append(message)

        await server(scope, receive, send)  # type: ignore[operator]
        return sent

    return _http_request


@pytest.fixture
def response_status() -> Callable[[list[Message]], int]:
    """Fixture: the status of the ``http.response.start`` message."""

    def _response_status(sent: list[Message]) -> int:
        return next(m["status"] for m in sent if m["type"] == "http.response.start")

    return _response_status


@pytest.fixture
def response_headers() -> Callable[[list[Message]], dict[bytes, bytes]]:
    """Fixture: the ``http.response.start`` headers as a byte-keyed dict."""

    def _response_headers(sent: list[Message]) -> dict[bytes, bytes]:
        start = next(m for m in sent if m["type"] == "http.response.start")
        return dict(start["headers"])

    return _response_headers


@pytest.fixture
def response_body() -> Callable[[list[Message]], bytes]:
    """Fixture: the concatenated ``http.response.body`` bytes."""

    def _response_body(sent: list[Message]) -> bytes:
        return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")

    return _response_body


class SseConnection:
    """A live SSE request: the response task plus the messages sent so far.

    ``sent[0]`` is the ``http.response.start``; each following message is one
    ``more_body`` chunk. The stream never ends on its own (the hub feed is
    infinite), so tests await the frames they expect and then ``close()`` —
    cancelling the response task, which unwinds the stream's ``finally``
    (hub unsubscribe).
    """

    def __init__(self, task: "asyncio.Task[None]", sent: list[Message]) -> None:
        self.task = task
        self.sent = sent

    def frames(self) -> list[bytes]:
        """The non-empty body chunks received so far (SSE wire records)."""
        return [
            m["body"]
            for m in self.sent
            if m["type"] == "http.response.body" and m.get("body")
        ]

    async def wait_frames(self, count: int, timeout: float = 2.0) -> list[bytes]:
        """Wait until ``count`` frames arrived (or fail the test on timeout)."""
        deadline = asyncio.get_running_loop().time() + timeout
        while len(self.frames()) < count:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(
                    f"expected {count} SSE frames, got {len(self.frames())}: {self.frames()!r}"
                )
            await asyncio.sleep(0.01)
        return self.frames()

    async def close(self) -> None:
        """Cancel the response task (client gone) and swallow the cancellation."""
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


@pytest.fixture
def sse_request() -> Callable[..., object]:
    """Fixture: open a GET request that stays live and collects SSE frames.

    ``receive`` never resolves after the initial ``http.request`` — the
    connection stays open the way a real SSE client holds it.
    """

    async def _sse_request(
        server: object,
        path: str = "/",
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> SseConnection:
        scope: Scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": list(headers or []),
        }
        sent: list[Message] = []
        started = asyncio.Event()

        async def receive() -> Message:
            if not started.is_set():
                started.set()
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()        # hold the connection open forever
            raise AssertionError("unreachable")

        async def send(message: Message) -> None:
            sent.append(message)

        task = asyncio.get_running_loop().create_task(server(scope, receive, send))  # type: ignore[operator]
        # wait for the http.response.start so callers can read headers at once
        deadline = asyncio.get_running_loop().time() + 2.0
        while not sent:
            if task.done():
                task.result()                   # surface the failure
                raise AssertionError("stream ended before http.response.start")
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("no http.response.start within 2s")
            await asyncio.sleep(0.01)
        return SseConnection(task, sent)

    return _sse_request
