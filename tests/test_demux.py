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

"""Demux, uvicorn boot and empty-websocket tests (SPECIFICATION.md §4, D3/D7).

The http tests boot the server on port 0 in a background thread, discover the
bound port from the uvicorn server state, and hit it with real httpx requests.
The websocket test drives ``BaseServer.__call__`` directly at the ASGI level:
the empty socket exists and closes cleanly without needing a websocket client.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from genro_asgi_core import BaseServer

from .throwaway_app import ThrowawayApp


@contextmanager
def running_server(server: BaseServer) -> Iterator[int]:
    """Boot ``server`` on port 0 in a background thread; yield the bound port."""
    thread = threading.Thread(target=lambda: server.serve(host="127.0.0.1", port=0), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while server.uvicorn_server is None or not server.uvicorn_server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start in time")
        time.sleep(0.01)
    port = server.uvicorn_server.servers[0].sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        server.uvicorn_server.should_exit = True
        thread.join(timeout=5)


@contextmanager
def booted() -> Iterator[int]:
    """A server with a primary and a secondary mounted as ``api`` (both throwaway)."""
    server = BaseServer(primary=ThrowawayApp(name="primary"))
    server.mount(ThrowawayApp(name="api", mount_name="api"))
    with running_server(server) as port:
        yield port


class TestDemux:
    def test_root_goes_to_primary(self) -> None:
        with booted() as port:
            r = httpx.get(f"http://127.0.0.1:{port}/")
            assert r.status_code == 200
            assert r.text == "primary:/"

    def test_unclaimed_first_segment_goes_to_primary(self) -> None:
        with booted() as port:
            r = httpx.get(f"http://127.0.0.1:{port}/nothing/claimed")
            assert r.status_code == 200
            assert r.text == "primary:/nothing/claimed"

    def test_mounted_first_segment_reaches_its_app_with_path_stripped(self) -> None:
        with booted() as port:
            r = httpx.get(f"http://127.0.0.1:{port}/api/echo")
            assert r.status_code == 200
            assert r.text == "api:/echo"

    def test_raising_route_returns_500_and_server_survives(self) -> None:
        with booted() as port:
            boom = httpx.get(f"http://127.0.0.1:{port}/boom")
            assert boom.status_code == 500
            healthy = httpx.get(f"http://127.0.0.1:{port}/")
            assert healthy.status_code == 200
            assert healthy.text == "primary:/"

    async def test_double_slash_before_a_mount_forwards_the_remainder(self) -> None:
        # the forwarded path is rebuilt from the same remainder used to find
        # the segment: //api/x reaches the mount as /x (driven at ASGI level)
        server = BaseServer(primary=ThrowawayApp(name="primary"))
        server.mount(ThrowawayApp(name="api", mount_name="api"))
        sent: list[dict[str, object]] = []

        async def receive() -> dict[str, object]:
            return {"type": "http.request"}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await server({"type": "http", "path": "//api/x"}, receive, send)

        body = next(m["body"] for m in sent if m["type"] == "http.response.body")
        assert body == b"api:/x"


class TestEmptyWebsocket:
    async def test_websocket_connect_is_closed_cleanly(self) -> None:
        server = BaseServer(primary=ThrowawayApp())
        sent: list[dict[str, object]] = []

        async def receive() -> dict[str, object]:
            return {"type": "websocket.connect"}

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        await server({"type": "websocket", "path": "/"}, receive, send)
        assert sent == [{"type": "websocket.close", "code": 1000}]
