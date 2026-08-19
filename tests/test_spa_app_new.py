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

"""The new front, from the outside: what a browser gets, and what the recipe builds.

Everything here goes through the doors production goes through — the recipe builds
the server, the lifespan builds the pool, an ASGI call gets an answer — because
this front's whole job is to be that seam. The pool below is a SUBCLASS whose
``serve_request`` is scripted: what the chain does with a request has its own
tests one folder over, and what belongs here is only what the front does with the
answer, or with the refusal.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import pytest
from genro_routes import route

from genro_asgi import AsgiServer
from genro_asgi.config.builder import AsgiConfigBuilder
from genro_asgi.applications.spa_app_new import (
    ERR_503_TEXT,
    STICKY_CID_COOKIE,
    ERR_502_TEXT,
    SpaApplicationNew,
)
from genro_asgi.spa.orchestration import AssignmentRefused, SiteFailedRequest, SpaCommander


class ScriptedCommander(SpaCommander):
    """A pool that answers from a script: no processes, no wire, no beat."""

    #: What the next request gets: a reply, or an exception raised instead.
    reply: dict[str, Any] = {"result": {"status": 200, "headers": [], "body": ""}}
    failure: Exception | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        #: One entry per request, as (cid, http).
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def serve_request(
        self, cid: str, http: dict[str, Any], *, hold_timeout: float
    ) -> dict[str, Any]:
        self.calls.append((cid, http))
        if self.failure is not None:
            raise self.failure
        return self.reply


class ScriptedFront(SpaApplicationNew):
    """The front under test: its own route, and a pool that answers from a script."""

    commander_class = ScriptedCommander

    @route()
    def ping(self) -> dict[str, bool]:
        return {"ping": True}


def recipe_for(root, fronts: int = 1) -> type[AsgiConfigBuilder]:
    """A recipe with the pool section and as many fronts as asked for."""

    class FrontConfig(AsgiConfigBuilder):
        def main(self, configuration_root: Any) -> None:
            cfg = configuration_root.configuration()
            applications = cfg.applications()
            for index in range(fronts):
                front = applications.application(
                    code=f"site{index}",
                    mount="" if not index else f"other{index}",
                    app_class=ScriptedFront,
                )
                # The pool belongs to the front that owns it: its words hang here.
                commander = front.commander(
                    frozen_users_path=str(root / f"frozen_users{index}"),
                    instance_dir=str(root / f"i{index}"),
                )
                groups = commander.groups(default="standard")
                groups.group(name="standard", entry_module="never.launched")

    return FrontConfig


class LifespanRunner:
    """The lifespan, driven the way a real ASGI runner drives it.

    The protocol is a conversation and not two calls: the server stays inside its
    lifespan scope between the startup and the shutdown, which is exactly the span
    a test wants to look at.
    """

    def __init__(self, server: AsgiServer) -> None:
        self.server = server
        self.sent: list[dict[str, Any]] = []
        self._inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._living: asyncio.Task[None] | None = None

    async def startup(self) -> None:
        self._living = asyncio.ensure_future(
            self.server({"type": "lifespan"}, self._inbox.get, self._send)
        )
        await self._inbox.put({"type": "lifespan.startup"})
        await self._answered("lifespan.startup.")

    async def shutdown(self) -> None:
        await self._inbox.put({"type": "lifespan.shutdown"})
        await self._living

    async def _send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    async def _answered(self, prefix: str) -> None:
        while not any(message["type"].startswith(prefix) for message in self.sent):
            await asyncio.sleep(0)


async def call(app: Any, path: str, cookie: str | None = None) -> dict[str, Any]:
    """One ASGI request, answered: the status, the headers and the body."""
    headers = [(b"host", b"site.example")]
    if cookie is not None:
        headers.append((b"cookie", f"{STICKY_CID_COOKIE}={cookie}".encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": headers,
        "scheme": "http",
        "client": ("10.0.0.1", 5555),
    }
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return {
        "status": start["status"],
        "headers": [(name.decode(), value.decode()) for name, value in start["headers"]],
        "body": body,
    }


def header_of(answer: dict[str, Any], name: str) -> str | None:
    """One header of an answer, by name."""
    return next((value for key, value in answer["headers"] if key.lower() == name), None)


@pytest.fixture
def server(tmp_path):
    """A server built from a recipe, with its front mounted and not yet started."""
    return AsgiServer(config=recipe_for(tmp_path))


@pytest.fixture
async def started(server):
    """The same server, through its own lifespan: the pool exists and is up."""
    runner = LifespanRunner(server)
    await runner.startup()
    yield server
    await runner.shutdown()


# -- the pool is born with the server --


async def test_the_pool_is_built_from_the_recipe_when_the_server_starts(server):
    front = server.applications["site0"]
    runner = LifespanRunner(server)

    with pytest.raises(RuntimeError):
        front.commander

    await runner.startup()

    assert isinstance(front.commander, ScriptedCommander)
    assert front.commander.started is True
    # What the recipe said, where it had to arrive.
    assert front.commander.default_group == "standard"
    assert set(front.commander.group_map) == {"standard"}

    await runner.shutdown()
    assert front.commander.started is False


async def test_two_fronts_each_own_their_pool(tmp_path):
    """A pool belongs to the front that owns it: two fronts are two pools."""
    server = AsgiServer(config=recipe_for(tmp_path, fronts=2))
    runner = LifespanRunner(server)

    await runner.startup()

    first = server.applications["site0"].commander
    second = server.applications["site1"].commander
    assert first is not second
    assert first.freeze_handler.root_path != second.freeze_handler.root_path

    await runner.shutdown()


# -- the demux --


async def test_its_own_route_answers_natively(started):
    front = started.applications["site0"]

    answer = await call(front, "/ping")

    assert answer["status"] == 200
    assert front.commander.calls == []


async def test_a_path_of_the_site_is_forwarded(started):
    front = started.applications["site0"]
    front.commander.reply = {
        "result": {
            "status": 201,
            "headers": [["content-type", "text/html"]],
            "body": base64.b64encode(b"<h1>the site</h1>").decode(),
        }
    }

    answer = await call(front, "/invoices/42")

    assert answer["status"] == 201
    assert answer["body"] == b"<h1>the site</h1>"
    assert header_of(answer, "content-type") == "text/html"
    cid, http = front.commander.calls[0]
    assert http["path"] == "/invoices/42"
    assert http["cid"] == cid


# -- the cookie --


async def test_a_request_with_no_cookie_is_answered_with_one(started):
    front = started.applications["site0"]

    answer = await call(front, "/invoices")

    cid, http = front.commander.calls[0]
    assert f"{STICKY_CID_COOKIE}={cid}" in header_of(answer, "set-cookie")
    # The site must see the connection this request already belongs to.
    assert any(
        name == "cookie" and f"{STICKY_CID_COOKIE}={cid}" in value for name, value in http["headers"]
    )


async def test_a_request_that_carries_the_cookie_is_answered_without_one(started):
    front = started.applications["site0"]

    answer = await call(front, "/invoices", cookie="c0ffee")

    assert header_of(answer, "set-cookie") is None
    assert front.commander.calls[0][0] == "c0ffee"


# -- the two refusals --


async def test_a_pool_that_takes_nobody_is_a_polite_503(started):
    front = started.applications["site0"]
    front.commander.failure = AssignmentRefused("mario", "no worker admits him", retry_after=30.0)

    answer = await call(front, "/invoices")

    assert answer["status"] == 503
    assert header_of(answer, "retry-after") == "30"
    assert answer["body"] == ERR_503_TEXT.encode()


async def test_the_inside_of_the_house_never_reaches_the_browser(started):
    front = started.applications["site0"]
    front.commander.failure = SiteFailedRequest(
        "mario", "ProgrammingError: relation invoices_2024 does not exist"
    )

    answer = await call(front, "/invoices")

    assert answer["status"] == 502
    assert answer["body"] == ERR_502_TEXT.encode()
    assert b"invoices_2024" not in answer["body"]


async def test_a_wire_that_is_gone_is_the_same_502(started):
    front = started.applications["site0"]
    front.commander.failure = ConnectionError("no child on the wire")

    answer = await call(front, "/invoices")

    assert answer["status"] == 502


async def test_a_refusal_still_answers_with_the_cookie_it_minted(started):
    front = started.applications["site0"]
    front.commander.failure = AssignmentRefused("mario", "no worker admits him", retry_after=30.0)

    answer = await call(front, "/invoices")

    cid = front.commander.calls[0][0]
    assert f"{STICKY_CID_COOKIE}={cid}" in header_of(answer, "set-cookie")
