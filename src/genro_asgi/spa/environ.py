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

"""The environ synthesizer: HTTP facts in, WSGI reply out, no transport.

The ratified modularity clause of design §3.1 asks for exactly this shape —
"dict in, dict out, testable without processes", never braided into the
envelope dispatch. :class:`WsgiSeam` is that isolated module: it takes the
``http`` dict a CALL carries, builds the PEP 3333 environ from it, invokes a
WSGI callable **as a library, in-process**, and shapes its answer back into a
dict. The WSGI adapter stays where the old code needs it and stops being a
transport; when the last WSGI piece goes dark this module goes with it and the
channel never notices.

**The wire shape, both ways.** The request dict is JSON-safe because the
channel is JSON: ``{"method", "path", "query_string", "headers", "body",
"client", "scheme"}`` — headers a pair-list so duplicates survive, body base64
like the move package. The reply is ``{"status", "headers", "body"}`` with the
same conventions.

**One body, whole, both ways.** Streaming and large bodies are out of scope by
ratification: the request body arrives as one ``BytesIO`` and the response
iterable is consumed to the last chunk (and closed, as PEP 3333 requires)
before the reply dict exists.

The call is synchronous — WSGI is — so the worker runs it on its pool.
"""

from __future__ import annotations

import base64
import io
import sys
from typing import Any, Callable, Iterable

__all__ = ["WsgiSeam"]

# The two headers PEP 3333 keeps out of the HTTP_ namespace.
UNPREFIXED_HEADERS = {"content-type": "CONTENT_TYPE", "content-length": "CONTENT_LENGTH"}


class WsgiSeam:
    """One WSGI callable, invoked in-process from the facts of a CALL."""

    def __init__(self, wsgi_app: Callable[..., Iterable[bytes]]) -> None:
        """Args:
        wsgi_app: the consumer's WSGI callable, ``(environ, start_response)``.
        """
        self.wsgi_app = wsgi_app
        self.status = ""
        self.headers: list[tuple[str, str]] = []

    def build_environ(self, http: dict[str, Any]) -> dict[str, Any]:
        """The PEP 3333 environ for one ``http`` dict.

        ``SCRIPT_NAME`` is empty: the path the front forwards is already
        mount-relative, so the whole of it is ``PATH_INFO``. ``SERVER_NAME`` and
        ``SERVER_PORT`` come from the Host header, the only place the front's
        own address survives the packing.
        """
        body = base64.b64decode(http.get("body") or "")
        headers = [(str(name), str(value)) for name, value in http.get("headers") or []]
        client = http.get("client") or []
        environ: dict[str, Any] = {
            "REQUEST_METHOD": http.get("method", "GET"),
            "SCRIPT_NAME": "",
            "PATH_INFO": http.get("path", "/"),
            "QUERY_STRING": http.get("query_string", ""),
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": http.get("scheme") or "http",
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": sys.stderr,
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }
        environ.update(self.header_environ(headers))
        if body and "CONTENT_LENGTH" not in environ:
            environ["CONTENT_LENGTH"] = str(len(body))
        host, port = self.server_address(environ.get("HTTP_HOST", ""))
        environ["SERVER_NAME"] = host
        environ["SERVER_PORT"] = port
        if client:
            environ["REMOTE_ADDR"] = str(client[0])
            if len(client) > 1:
                environ["REMOTE_PORT"] = str(client[1])
        return environ

    def header_environ(self, headers: list[tuple[str, str]]) -> dict[str, str]:
        """The header half of the environ: ``HTTP_*`` keys, duplicates joined.

        A repeated header is one environ key holding the values comma-joined —
        the reassembly PEP 3333 prescribes, and the reason the wire carries a
        pair-list instead of a mapping. ``Cookie`` is the one exception: its
        pairs rejoin with ``"; "`` (RFC 6265, restated by RFC 7540 §8.1.2.5) —
        a comma would fuse two cookies into one mangled value.
        """
        packed: dict[str, str] = {}
        for name, value in headers:
            key = UNPREFIXED_HEADERS.get(name.lower()) or f"HTTP_{name.upper().replace('-', '_')}"
            if key in packed:
                joiner = "; " if key == "HTTP_COOKIE" else ","
                packed[key] = f"{packed[key]}{joiner}{value}"
            else:
                packed[key] = value
        return packed

    def server_address(self, host_header: str) -> tuple[str, str]:
        """Split a Host header into ``(SERVER_NAME, SERVER_PORT)``."""
        if not host_header:
            return "localhost", "80"
        host, _, port = host_header.partition(":")
        return host, port or "80"

    def start_response(
        self,
        status: str,
        headers: list[tuple[str, str]],
        exc_info: Any = None,
    ) -> Callable[[bytes], None]:
        """The classic WSGI callback: capture status and headers for the reply.

        The return value is the legacy ``write`` callable PEP 3333 still
        mandates; nothing here uses it, so it raises rather than pretending to
        buffer bytes the reply would silently lose.
        """
        self.status = status
        self.headers = list(headers)
        return self.refuse_write

    def refuse_write(self, data: bytes) -> None:
        """The deprecated ``write`` callable — unsupported, and says so."""
        raise NotImplementedError("the write() callable is not supported: return an iterable")

    def serve(self, http: dict[str, Any]) -> dict[str, Any]:
        """Run the WSGI app on one ``http`` dict and shape its reply.

        Synchronous by nature — the caller gives it a thread.
        """
        environ = self.build_environ(http)
        result = self.wsgi_app(environ, self.start_response)
        try:
            body = b"".join(result)
        finally:
            close = getattr(result, "close", None)
            if close is not None:
                close()
        return {
            "status": int(self.status.split(" ", 1)[0]),
            "headers": [[name, value] for name, value in self.headers],
            "body": base64.b64encode(body).decode("ascii"),
        }
