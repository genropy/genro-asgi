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

"""The mountable SPA front: an application that owns a user-sticky pool.

``SpaApplication`` is a ``RoutedApplication`` — its own router faces the SITE,
so ``@route`` methods on a subclass answer natively — and it OWNS a
``UserStickyCommander`` as ``self.commander`` (composition, ratified
2026-08-08: the commander stays a derivable base and never becomes an
application, keeping the two namespaces and the two lifecycles apart).

Constructor kwargs are split in two: the commander's own — the exact signature
of ``UserStickyCommander.__init__`` — are peeled and handed to the pool; every
other kwarg travels up the cooperative constructor chain to
``RoutedApplication``/``BaseApplication`` (``code``, ``mount``, ``db_name``).
Only the names actually passed are forwarded, so the commander's defaults keep
answering for the rest. ``commander_class`` chooses the pool type; it is a
Python type and not a dotted string because the commander lives in THIS
process, unlike ``worker_class`` which crosses the process boundary.

The ``application(...)`` config element is open-signature, so the single role
of issue #3 — ``workers=0, local_worker=True`` — reaches the commander through
the stock config recipe with no new grammar.

The pool's lifecycle is the application's: ``on_startup`` starts it,
``on_shutdown`` stops it.

Serving is a two-stage demux, transcribed from the legacy front. Stage 1 reads
the FIRST segment of the (already mount-relative) request path: not one of
``internal_roots`` — the app's own first-level roots — and the path belongs to
the hosted site, forwarded to the pool. Stage 2 resolves the FULL path in the
app's own router: the node exists, so the request is served natively; a
structural miss under a claimed root belongs to the site after all and falls
through. ``resolves_natively`` asks the router WITHOUT auth filters, so a route
that exists but would be denied still answers its own 403 natively and never
falls through — the fallback is on non-existence ONLY, which is what keeps a
protected native route from leaking the site behind it.

``internal_roots`` is recomputed per access (no snapshot, so attach order never
matters) over the STRUCTURAL view of the router (``forbidden=True``): a gated
route is still a claimed root. ``index`` is excluded — the inherited splash
handler must not claim ``/index/...`` away from the site.

**The forward.** A request that belongs to the site is packed into the ``http``
CALL form and handed to the pool through ``commander.forward_envelope`` — the
front adds no routing of its own, so the sticky pick, the placement wait, the
event fold and the delivery merge all stay where they already live.

A forward the pool refuses — no worker for the identity, a dead one, an error
REPLY — raises ``ChannelCallError`` and becomes a text/plain **502**: the site
is the gateway's upstream, and its unavailability is not the client's error.

The sticky key is the ``sticky_cid`` cookie, read ONCE per request and handed
down the packing (nothing parses it twice), minted here when the request
carries none. The IDENTITY the forward routes on is read off the commander's
own surface — ``connection_user.get(cid, cid)``: the session id while
anonymous, the real user once a login has been folded. The front keeps ZERO
state of its own; the fold is the single writer, and the front only reads it.

The cookie is issued when this request minted the cid, and re-issued when the
fold registered a birth for it (the legacy ``birth_cookies``, observed through
the surface the fold writes rather than through the raw event list, which the
commander's envelope does not carry).

The outer response is built from ``envelope["result"]`` alone. A forwarded
request is never page-addressed, so its envelope carries no delivery
(``DELIVERY_KEYS``); if one ever appears, the front raises — no rail from the
front to the browser is ratified, and header transport is abolished on record
(2026-08-02), so none may be improvised here.
"""

from __future__ import annotations

import base64
import inspect
import uuid
from typing import TYPE_CHECKING, Any

from ..channel.hub import ChannelCallError
from ..middleware.base import cookie_value
from ..response import Response
from ..routed_application import RoutedApplication
from ..spa.commander import UserStickyCommander
from ..spa.worker import DELIVERY_KEYS

if TYPE_CHECKING:
    from ..types import Receive, Scope, Send

#: The connection cookie, legacy name and legacy attributes.
STICKY_CID_COOKIE = "sticky_cid"

#: The base commander's own constructor kwargs, peeled off before the chain.
#: A ``commander_class`` subclass extends this set with its OWN signature —
#: the peel is by name, so a name behind a subclass ``**kwargs`` still peels.
COMMANDER_KWARGS = (
    "workers",
    "path",
    "host",
    "port",
    "group",
    "worker_class",
    "worker_kwargs",
    "executable",
    "max_workers",
    "guest_occupancy_limit",
    "probe_interval",
    "probe_timeout",
    "local_worker",
)


class SpaApplication(RoutedApplication):
    """A single-page-application front backed by a user-sticky worker pool."""

    def __init__(self, **kwargs: Any) -> None:
        commander_class: type[UserStickyCommander] = kwargs.pop(
            "commander_class", UserStickyCommander
        )
        peel: set[str] = set(COMMANDER_KWARGS)
        peel.update(
            parameter.name
            for parameter in inspect.signature(commander_class.__init__).parameters.values()
            if parameter.kind in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY)
            and parameter.name != "self"
        )
        commander_kwargs = {name: kwargs.pop(name) for name in list(kwargs) if name in peel}
        self._commander_class = commander_class
        self._commander = commander_class(**commander_kwargs)
        super().__init__(**kwargs)

    @property
    def commander_class(self) -> type[UserStickyCommander]:
        """The pool type this application was built with."""
        return self._commander_class

    @property
    def commander(self) -> UserStickyCommander:
        """The user-sticky pool this application owns."""
        return self._commander

    @property
    def internal_roots(self) -> set[str]:
        """The app's OWN first-level roots, minus ``index``.

        Recomputed per access from the STRUCTURAL router view
        (``forbidden=True``): a route hidden by a plugin filter is still a
        claimed root, so it can never fall through to the hosted site.
        """
        nodes = self.route.nodes(lazy=True, forbidden=True)
        return (set(nodes.get("entries", {})) | set(nodes.get("routers", {}))) - {"index"}

    def resolves_natively(self, path: str) -> bool:
        """Whether ``path`` resolves to an EXISTING node in the app's router.

        The structural half of the demux: resolution runs with NO auth filters,
        so the answer is purely "does this node exist?" — the same best-match
        candidate resolution (``*args`` handlers included) the native dispatch
        would use. Only a genuine ``not_found`` is a miss; an existing node a
        filter would deny still answers True and stays native.
        """
        return bool(self.route.node(path).error != "not_found")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Demultiplex: the app's own router, else the hosted site."""
        path = str(scope.get("path", "/"))
        first_segment = path.strip("/").split("/")[0]
        if first_segment in self.internal_roots and self.resolves_natively(path):
            await super().__call__(scope, receive, send)
        else:
            await self.forward_request(scope, receive, send)

    async def forward_request(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve a site path through the pool: pack, forward, translate, answer.

        The cookie is read ONCE here and the fact travels down: ``pack_http``
        and ``pack_headers`` receive whether the request carried one instead of
        re-scanning the headers for it.

        A CALL the worker answers with an error REPLY — ``ChannelCallError``,
        the one refusal this forward translates (ratified perimeter) — is a bad
        gateway: the error text becomes a text/plain 502 body, and the cookie
        logic applies to it like to any other answer, so the connection this
        request minted survives the failure. Any other exception is the
        server's own 500, not a gateway answer.
        """
        carried = self.request_cid(scope)
        cid = carried or uuid.uuid4().hex
        known = cid in self.commander.connection_user
        http = await self.pack_http(scope, receive, cid, carried)
        try:
            envelope = await self.commander.forward_envelope(
                self.forward_identity(cid), str(scope.get("path", "/")), {"http": http}
            )
        except ChannelCallError as exc:
            born = not known and cid in self.commander.connection_user
            response = self.gateway_response(exc, cid, carried is None or born)
        else:
            born = not known and cid in self.commander.connection_user
            response = self.build_response(envelope, cid, carried is None or born)
        await response(scope, receive, send)

    def gateway_response(self, exc: ChannelCallError, cid: str, issue_cookie: bool) -> Response:
        """The 502 a refused forward becomes: the pool's error text, as text/plain."""
        payload = getattr(exc, "payload", None) or {}
        response = Response(
            content=str(payload.get("error") or exc),
            status_code=502,
            headers=[("content-type", "text/plain; charset=utf-8")],
        )
        return self.stamp_cookie(response, cid, issue_cookie)

    def stamp_cookie(self, response: Response, cid: str, issue_cookie: bool) -> Response:
        """The one tail that writes the sticky cookie, whatever exit built the response."""
        if issue_cookie:
            response.set_cookie(STICKY_CID_COOKIE, cid, path="/", httponly=True, samesite="lax")
        return response

    def request_cid(self, scope: Scope) -> str | None:
        """The ``sticky_cid`` this request carries, or ``None`` when it carries none."""
        return cookie_value(scope, STICKY_CID_COOKIE)

    def forward_identity(self, cid: str) -> str:
        """The sticky key to route on: the user once folded, the cid while anonymous."""
        return self.commander.connection_user.get(cid, cid)

    async def read_body(self, receive: Receive) -> bytes:
        """Drain the whole request body off the ASGI receive channel."""
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"") or b""
            if not message.get("more_body", False):
                break
        return body

    async def pack_http(
        self, scope: Scope, receive: Receive, cid: str, carried: str | None
    ) -> dict[str, Any]:
        """Pack the ASGI request into the JSON-safe ``http`` CALL form.

        The cid the front just decided travels in the forwarded ``cookie``
        header: a minted one is not on the client's request yet, and the hosted
        site must see the connection this request already belongs to.
        ``carried`` is the cookie the forward already parsed, handed down so
        nothing reads it a second time.
        """
        query_string = scope.get("query_string") or b""
        client = scope.get("client") or None
        return {
            "method": str(scope.get("method", "GET")),
            "path": str(scope.get("path", "/")),
            "query_string": query_string.decode("latin-1"),
            "headers": self.pack_headers(scope, cid, carried),
            "body": base64.b64encode(await self.read_body(receive)).decode("ascii"),
            "client": list(client) if client else [],
            "scheme": str(scope.get("scheme", "http")),
        }

    def pack_headers(self, scope: Scope, cid: str, carried: str | None) -> list[list[str]]:
        """The request headers as a pair-list, with ``sticky_cid`` guaranteed present.

        ``carried`` is the cookie value the forward parsed: a request that
        already carries one needs no touch-up. A minted cid JOINS the request's
        own ``cookie`` header (``"; "``, RFC 6265) — a second ``cookie`` pair
        would be comma-joined by the PEP 3333 reassembly on the serving side,
        mangling every cookie in it.
        """
        headers = [
            [name.decode("latin-1"), value.decode("latin-1")]
            for name, value in scope.get("headers") or []
        ]
        if carried is None:
            for pair in headers:
                if pair[0] == "cookie":
                    pair[1] = f"{pair[1]}; {STICKY_CID_COOKIE}={cid}"
                    break
            else:
                headers.append(["cookie", f"{STICKY_CID_COOKIE}={cid}"])
        return headers

    def build_response(self, envelope: dict[str, Any], cid: str, issue_cookie: bool) -> Response:
        """The outer response, built from ``envelope["result"]`` alone.

        The reply dict is the site's whole answer — status, headers, body.
        A forward is never page-addressed, so delivery cannot appear in its
        envelope; one arriving means an unratified rail and raises.
        """
        if any(key in envelope for key in DELIVERY_KEYS):
            raise NotImplementedError(
                "a front forward carries no delivery: "
                "no rail from the front to the browser is ratified"
            )
        reply = envelope["result"]
        response = Response(
            content=base64.b64decode(reply.get("body") or ""),
            status_code=int(reply.get("status", 200)),
            headers=[(str(name), str(value)) for name, value in reply.get("headers") or []],
        )
        return self.stamp_cookie(response, cid, issue_cookie)

    async def on_startup(self) -> None:
        """Start the owned pool with the server."""
        await self.commander.start()

    async def on_shutdown(self) -> None:
        """Stop the owned pool with the server."""
        await self.commander.stop()
