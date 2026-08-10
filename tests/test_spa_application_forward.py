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

"""The forward: sticky cookie, identity, pack/unpack, the no-delivery guard.

The pool is a stub here — it records what the front handed it and answers with
a canned envelope — so what is pinned is the front's own half: which identity
the forward routes on, when the ``sticky_cid`` cookie is issued, how the ASGI
request becomes the ``http`` CALL form and how the reply becomes the outer
response. The one worker-side assertion is that the nested form the commander's
envelope produces still reaches the WSGI seam.
"""

from __future__ import annotations

import base64
from typing import Any, Callable, Iterable

import pytest

from genro_asgi.applications import SpaApplication
from genro_asgi.applications.spa_app import STICKY_CID_COOKIE
from genro_asgi.channel.hub import ChannelCallError
from genro_asgi.spa.worker import UserStickyWorker
from genro_asgi.types import Message, Receive, Scope

from .test_spa_http_form import RecordingChannel, call_frame, http_form


class StubCommander:
    """A pool that records the forward and answers with a canned envelope."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.connection_user: dict[str, str] = {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.envelope: dict[str, Any] = {"result": reply_form()}
        self.births: dict[str, str] = {}
        self.failure: Exception | None = None

    async def forward_envelope(
        self, identity: str, path: str, kwargs: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append((identity, path, kwargs or {}))
        # the fold the real commander runs inside forward_envelope
        self.connection_user.update(self.births)
        if self.failure is not None:
            raise self.failure
        return self.envelope

    @property
    def http(self) -> dict[str, Any]:
        """The ``http`` form of the last forward."""
        return dict(self.calls[-1][2]["http"])


def reply_form(**overrides: Any) -> dict[str, Any]:
    """A minimal well-formed reply dict, overridable field by field."""
    reply = {
        "status": 200,
        "headers": [["content-type", "text/html"]],
        "body": base64.b64encode(b"<html/>").decode("ascii"),
    }
    reply.update(overrides)
    return reply


def make_spa(**kwargs: Any) -> SpaApplication:
    return SpaApplication(mount="", workers=0, commander_class=StubCommander, **kwargs)


def site_scope(
    path: str = "/sales/order",
    headers: list[tuple[bytes, bytes]] | None = None,
    **overrides: Any,
) -> Scope:
    """An ASGI scope for a path the front does not claim."""
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": headers if headers is not None else [(b"host", b"example.org")],
        "client": ("10.0.0.7", 5000),
        "scheme": "http",
    }
    scope.update(overrides)
    return scope


def body_receive(*chunks: bytes) -> Receive:
    """A receive channel handing out ``chunks``, the last one terminal."""
    pending = list(chunks) or [b""]

    async def receive() -> Message:
        chunk = pending.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(pending)}

    return receive


class Sent:
    """Collects what the response emitted."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def __call__(self, message: Message) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int:
        return int(self.messages[0]["status"])

    @property
    def headers(self) -> list[tuple[str, str]]:
        return [
            (name.decode("latin-1"), value.decode("latin-1"))
            for name, value in self.messages[0]["headers"]
        ]

    @property
    def body(self) -> bytes:
        return bytes(self.messages[1]["body"])

    def header_values(self, name: str) -> list[str]:
        return [value for key, value in self.headers if key == name]


async def forward(spa: SpaApplication, scope: Scope | None = None, *chunks: bytes) -> Sent:
    """Run one site request through the front and collect the response."""
    sent = Sent()
    await spa(scope if scope is not None else site_scope(), body_receive(*chunks), sent)
    return sent


def cookie_header(cid: str) -> list[tuple[bytes, bytes]]:
    return [(b"host", b"example.org"), (b"cookie", f"{STICKY_CID_COOKIE}={cid}".encode())]


# ----------------------------------------------------------------------
# The identity the forward routes on
# ----------------------------------------------------------------------


async def test_an_anonymous_request_routes_on_its_own_cid() -> None:
    spa = make_spa()
    await forward(spa, site_scope(headers=cookie_header("cid-1")))
    identity, path, _ = spa.commander.calls[0]
    assert identity == "cid-1"
    assert path == "/sales/order"


async def test_after_the_login_fold_the_forward_routes_on_the_real_user() -> None:
    spa = make_spa()
    spa.commander.connection_user["cid-1"] = "alice"
    await forward(spa, site_scope(headers=cookie_header("cid-1")))
    assert spa.commander.calls[0][0] == "alice"


async def test_a_minted_cid_is_its_own_identity() -> None:
    spa = make_spa()
    sent = await forward(spa)
    minted = spa.commander.calls[0][0]
    assert len(minted) == 32
    assert f"{STICKY_CID_COOKIE}={minted}" in sent.header_values("set-cookie")[0]


# ----------------------------------------------------------------------
# The sticky cookie
# ----------------------------------------------------------------------


async def test_a_request_without_a_cookie_gets_one_minted() -> None:
    spa = make_spa()
    sent = await forward(spa)
    cookie = sent.header_values("set-cookie")[0]
    assert cookie.startswith(f"{STICKY_CID_COOKIE}=")
    assert "Path=/" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Max-Age" not in cookie
    assert "Secure" not in cookie


async def test_a_carried_cid_is_not_re_issued_when_nothing_was_born() -> None:
    spa = make_spa()
    spa.commander.connection_user["cid-1"] = "alice"
    sent = await forward(spa, site_scope(headers=cookie_header("cid-1")))
    assert sent.header_values("set-cookie") == []


async def test_a_carried_cid_is_re_issued_when_the_fold_registers_its_birth() -> None:
    spa = make_spa()
    spa.commander.births["cid-1"] = "cid-1"
    sent = await forward(spa, site_scope(headers=cookie_header("cid-1")))
    assert sent.header_values("set-cookie") == [
        f"{STICKY_CID_COOKIE}=cid-1; Path=/; HttpOnly; SameSite=Lax"
    ]


async def test_the_cid_the_front_decided_rides_the_forwarded_cookie_header() -> None:
    spa = make_spa()
    await forward(spa)
    minted = spa.commander.calls[0][0]
    cookies = [value for name, value in spa.commander.http["headers"] if name == "cookie"]
    assert cookies == [f"{STICKY_CID_COOKIE}={minted}"]


async def test_a_carried_cookie_is_forwarded_once_untouched() -> None:
    spa = make_spa()
    await forward(spa, site_scope(headers=cookie_header("cid-1")))
    cookies = [value for name, value in spa.commander.http["headers"] if name == "cookie"]
    assert cookies == [f"{STICKY_CID_COOKIE}=cid-1"]


async def test_a_minted_cid_joins_the_existing_cookie_header() -> None:
    spa = make_spa()
    headers = [(b"host", b"example.org"), (b"cookie", b"theme=dark")]
    await forward(spa, site_scope(headers=headers))
    minted = spa.commander.calls[0][0]
    cookies = [value for name, value in spa.commander.http["headers"] if name == "cookie"]
    assert cookies == [f"theme=dark; {STICKY_CID_COOKIE}={minted}"]


async def test_a_malformed_sibling_cookie_never_costs_the_carried_cid() -> None:
    spa = make_spa()
    headers = [
        (b"host", b"example.org"),
        (b"cookie", f"bad{{k}}=x; {STICKY_CID_COOKIE}=cid-1".encode()),
    ]
    await forward(spa, site_scope(headers=headers))
    assert spa.commander.calls[0][0] == "cid-1"


# ----------------------------------------------------------------------
# Packing the request
# ----------------------------------------------------------------------


async def test_the_request_facts_reach_the_http_form() -> None:
    spa = make_spa()
    scope = site_scope(method="POST", query_string=b"a=1&b=2", scheme="https")
    await forward(spa, scope, b"payload")
    http = spa.commander.http
    assert http["method"] == "POST"
    assert http["path"] == "/sales/order"
    assert http["query_string"] == "a=1&b=2"
    assert http["scheme"] == "https"
    assert http["client"] == ["10.0.0.7", 5000]
    assert base64.b64decode(http["body"]) == b"payload"


async def test_a_chunked_body_is_drained_whole() -> None:
    spa = make_spa()
    await forward(spa, site_scope(method="POST"), b"one ", b"two ", b"three")
    assert base64.b64decode(spa.commander.http["body"]) == b"one two three"


async def test_duplicate_request_headers_survive_the_pair_list() -> None:
    spa = make_spa()
    headers = [(b"host", b"example.org"), (b"accept", b"a"), (b"accept", b"b")]
    await forward(spa, site_scope(headers=headers))
    accepted = [value for name, value in spa.commander.http["headers"] if name == "accept"]
    assert accepted == ["a", "b"]


# ----------------------------------------------------------------------
# Unpacking the reply
# ----------------------------------------------------------------------


async def test_the_reply_becomes_the_outer_response() -> None:
    spa = make_spa()
    spa.commander.envelope = {
        "result": reply_form(
            status=404,
            headers=[["content-type", "text/plain"], ["x-site", "yes"]],
            body=base64.b64encode(b"missing").decode("ascii"),
        )
    }
    sent = await forward(spa, site_scope(headers=cookie_header("cid-1")))
    assert sent.status == 404
    assert sent.body == b"missing"
    assert ("content-type", "text/plain") in sent.headers
    assert ("x-site", "yes") in sent.headers


async def test_an_empty_body_reply_answers_empty() -> None:
    spa = make_spa()
    spa.commander.envelope = {"result": reply_form(status=204, body="")}
    sent = await forward(spa, site_scope(headers=cookie_header("cid-1")))
    assert sent.status == 204
    assert sent.body == b""


# ----------------------------------------------------------------------
# Delivery — a forward is never page-addressed, the guard raises
# ----------------------------------------------------------------------


async def test_a_forward_envelope_carrying_delivery_raises() -> None:
    spa = make_spa()
    spa.commander.envelope = {
        "result": reply_form(),
        "datachanges": "the-changes",
        "dbevents": "the-events",
    }
    with pytest.raises(NotImplementedError):
        await forward(spa, site_scope(headers=cookie_header("cid-1")))


# ----------------------------------------------------------------------
# A refused forward is a bad gateway
# ----------------------------------------------------------------------


async def test_a_refused_forward_becomes_a_502_carrying_the_pools_error() -> None:
    spa = make_spa()
    spa.commander.failure = ChannelCallError(
        "W:w1", "/sales/order", "worker is gone", payload={"error": "worker is gone"}
    )
    sent = await forward(spa, site_scope(headers=cookie_header("cid-1")))
    assert sent.status == 502
    assert sent.body == b"worker is gone"
    assert sent.header_values("content-type") == ["text/plain; charset=utf-8"]


async def test_a_502_still_issues_the_cookie_of_a_minted_cid() -> None:
    spa = make_spa()
    spa.commander.failure = ChannelCallError("W:w1", "/sales/order", "boom")
    sent = await forward(spa)
    assert sent.status == 502
    assert len(sent.header_values("set-cookie")) == 1


# ----------------------------------------------------------------------
# The worker end of the forward
# ----------------------------------------------------------------------


async def test_the_nested_http_form_the_envelope_produces_reaches_the_seam() -> None:
    served: dict[str, Any] = {}

    def site(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        served.update(environ)
        start_response("200 OK", [("content-type", "text/plain")])
        return [b"served"]

    worker = UserStickyWorker("W:w1")
    worker.attach_channel(RecordingChannel())
    worker.wsgi_app = site
    payload = {"identity": "alice", "kwargs": {"http": http_form()}}
    await worker.service_call(call_frame(payload))
    reply = worker.channel.frames[0].data
    assert reply["result"]["status"] == 200
    assert served["PATH_INFO"] == "/sales/order"
    await worker.shutdown()
