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

"""The http CALL form: environ synthesis and the worker-side WSGI seam.

Two halves, tested apart. :class:`WsgiSeam` is dict in, dict out — no worker,
no channel, no process — so the PEP 3333 keys, the header reassembly and the
reply shaping are asserted directly on it. The worker half asserts only the
routing: an http payload reaches ``serve_http``, an empty seam still answers
the explicit error, and a raising WSGI app becomes an error REPLY like any
other failed CALL.
"""

from __future__ import annotations

import base64
from typing import Any, Callable, Iterable

from genro_asgi.channel import Frame
from genro_asgi.channel.hub import CALL_METHOD
from genro_asgi.spa.environ import WsgiSeam
from genro_asgi.spa.worker import UserStickyWorker


def http_form(**overrides: Any) -> dict[str, Any]:
    """A minimal well-formed ``http`` dict, overridable field by field."""
    form: dict[str, Any] = {
        "method": "GET",
        "path": "/sales/order",
        "query_string": "id=7",
        "headers": [["host", "example.org:8080"]],
        "body": "",
        "client": ["10.0.0.9", 51234],
        "scheme": "http",
    }
    form.update(overrides)
    return form


def packed(body: bytes) -> str:
    """The wire form of a request body."""
    return base64.b64encode(body).decode("ascii")


class EchoApp:
    """A WSGI app that reports the environ it was given, as JSON-ish text."""

    def __init__(self, status: str = "200 OK", headers: list[tuple[str, str]] | None = None) -> None:
        self.status = status
        self.headers = headers if headers is not None else [("Content-Type", "text/plain")]
        self.environ: dict[str, Any] = {}
        self.body = b""

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        self.environ = environ
        self.body = environ["wsgi.input"].read()
        start_response(self.status, self.headers)
        return [b"echoed"]


class ChunkedApp:
    """A WSGI app answering in several chunks, and recording its close()."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.closed = False

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        start_response("201 Created", [("X-Chunks", str(len(self.chunks)))])
        return self

    def __iter__(self) -> Any:
        return iter(self.chunks)

    def close(self) -> None:
        self.closed = True


class RecordingChannel:
    """The member face reduced to what ``send_reply`` needs: it keeps the frames."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []
        self.on_message: Any = None

    async def send_frame(self, frame: Frame) -> str:
        self.frames.append(frame)
        return frame.id

    async def close(self) -> None:
        pass


def call_frame(payload: dict[str, Any], path: str = "/op/serve") -> Frame:
    """One inbound CALL frame carrying ``payload``."""
    return Frame(id="c1", method=CALL_METHOD, path=path, data=payload)


# ----------------------------------------------------------------------
# The environ: PEP 3333 keys from the facts of the CALL
# ----------------------------------------------------------------------


def test_the_request_line_and_the_scheme_become_environ_keys() -> None:
    environ = WsgiSeam(EchoApp()).build_environ(http_form(method="POST", scheme="https"))
    assert environ["REQUEST_METHOD"] == "POST"
    assert environ["SCRIPT_NAME"] == ""
    assert environ["PATH_INFO"] == "/sales/order"
    assert environ["QUERY_STRING"] == "id=7"
    assert environ["wsgi.url_scheme"] == "https"
    assert environ["wsgi.version"] == (1, 0)
    assert environ["wsgi.multithread"] is True
    assert environ["wsgi.run_once"] is False


def test_the_host_header_becomes_the_server_address() -> None:
    environ = WsgiSeam(EchoApp()).build_environ(http_form())
    assert environ["SERVER_NAME"] == "example.org"
    assert environ["SERVER_PORT"] == "8080"
    assert environ["HTTP_HOST"] == "example.org:8080"


def test_a_hostless_request_falls_back_to_localhost_and_port_80() -> None:
    environ = WsgiSeam(EchoApp()).build_environ(http_form(headers=[]))
    assert (environ["SERVER_NAME"], environ["SERVER_PORT"]) == ("localhost", "80")


def test_the_client_pair_becomes_remote_addr_and_port() -> None:
    environ = WsgiSeam(EchoApp()).build_environ(http_form())
    assert environ["REMOTE_ADDR"] == "10.0.0.9"
    assert environ["REMOTE_PORT"] == "51234"


def test_content_headers_keep_the_unprefixed_names_pep3333_mandates() -> None:
    form = http_form(
        headers=[["content-type", "application/json"], ["content-length", "2"]],
        body=packed(b"{}"),
    )
    environ = WsgiSeam(EchoApp()).build_environ(form)
    assert environ["CONTENT_TYPE"] == "application/json"
    assert environ["CONTENT_LENGTH"] == "2"
    assert "HTTP_CONTENT_TYPE" not in environ


def test_a_body_without_a_content_length_header_gets_its_measured_length() -> None:
    environ = WsgiSeam(EchoApp()).build_environ(http_form(body=packed(b"hello")))
    assert environ["CONTENT_LENGTH"] == "5"
    assert environ["wsgi.input"].read() == b"hello"


def test_duplicate_headers_survive_the_pair_list_and_are_comma_joined() -> None:
    form = http_form(headers=[["accept", "a"], ["Accept", "b"], ["host", "h"]])
    environ = WsgiSeam(EchoApp()).build_environ(form)
    assert environ["HTTP_ACCEPT"] == "a,b"


def test_duplicate_cookie_headers_rejoin_with_a_semicolon() -> None:
    # RFC 6265: cookie-pairs rejoin with "; " — a comma would fuse two cookies
    form = http_form(headers=[["cookie", "a=1"], ["Cookie", "b=2"], ["host", "h"]])
    environ = WsgiSeam(EchoApp()).build_environ(form)
    assert environ["HTTP_COOKIE"] == "a=1; b=2"


# ----------------------------------------------------------------------
# The seam: one WSGI call, one reply dict
# ----------------------------------------------------------------------


def test_the_reply_carries_the_status_the_headers_and_the_base64_body() -> None:
    app = EchoApp(status="404 Not Found", headers=[("X-A", "1"), ("X-A", "2")])
    reply = WsgiSeam(app).serve(http_form())
    assert reply["status"] == 404
    assert reply["headers"] == [["X-A", "1"], ["X-A", "2"]]
    assert base64.b64decode(reply["body"]) == b"echoed"


def test_the_request_body_reaches_the_app_whole() -> None:
    app = EchoApp()
    WsgiSeam(app).serve(http_form(method="POST", body=packed(b'{"a": 1}')))
    assert app.body == b'{"a": 1}'
    assert app.environ["REQUEST_METHOD"] == "POST"


def test_a_chunked_answer_is_joined_and_the_iterable_is_closed() -> None:
    app = ChunkedApp([b"one ", b"two ", b"three"])
    reply = WsgiSeam(app).serve(http_form())
    assert reply["status"] == 201
    assert base64.b64decode(reply["body"]) == b"one two three"
    assert app.closed is True


def test_the_write_callable_is_refused_rather_than_silently_dropped() -> None:
    seam = WsgiSeam(EchoApp())
    write = seam.start_response("200 OK", [])
    try:
        write(b"lost bytes")
    except NotImplementedError as exc:
        assert "write()" in str(exc)
    else:
        raise AssertionError("the write callable answered instead of refusing")


# ----------------------------------------------------------------------
# The worker half: the form routes to the seam, or says the seam is empty
# ----------------------------------------------------------------------


async def test_an_http_call_is_served_by_the_workers_wsgi_app() -> None:
    worker = UserStickyWorker("W:w1")
    worker.attach_channel(RecordingChannel())
    app = EchoApp()
    worker.wsgi_app = app
    await worker.service_call(call_frame({"identity": "alice", "http": http_form()}))
    reply = worker.channel.frames[0].data
    assert reply["result"]["status"] == 200
    assert base64.b64decode(reply["result"]["body"]) == b"echoed"
    assert app.environ["PATH_INFO"] == "/sales/order"
    await worker.shutdown()


async def test_an_http_call_without_a_wsgi_app_still_answers_the_explicit_error() -> None:
    worker = UserStickyWorker("W:w1")
    worker.attach_channel(RecordingChannel())
    assert worker.wsgi_app is None
    await worker.service_call(call_frame({"identity": "alice", "http": http_form()}))
    assert worker.channel.frames[0].data["error"] == "http CALL form is unsupported until phase B"


async def test_a_raising_wsgi_app_becomes_an_error_reply() -> None:
    def boom(environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        raise RuntimeError("site exploded")

    worker = UserStickyWorker("W:w1")
    worker.attach_channel(RecordingChannel())
    worker.wsgi_app = boom
    await worker.service_call(call_frame({"identity": "alice", "http": http_form()}))
    assert worker.channel.frames[0].data["error"] == "RuntimeError: site exploded"
    await worker.shutdown()


async def test_an_op_call_with_an_http_shaped_kwarg_is_still_the_op() -> None:
    # the ops' **fields are an open namespace: a field named "http" must never
    # divert a routed op onto the WSGI seam
    worker = UserStickyWorker("W:w1")
    worker.attach_channel(RecordingChannel())
    frame = call_frame(
        {"identity": "s1", "kwargs": {"http": "1.1", "user_agent": "x"}},
        path="/op/new_connection",
    )
    await worker.service_call(frame)
    reply = worker.channel.frames[0].data
    assert "error" not in reply
    assert reply["result"]["user"] == "s1"
    await worker.shutdown()
