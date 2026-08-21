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

"""The mountable front of the new orchestration: one door, and no state at all.

It stands BESIDE ``SpaApplication``, which serves the real traffic until the
cutover: nothing here imports that module and nothing there imports this one, the
same isolation the three macros before this one kept. The two die together, one
of them of old age.

**The pool is born with the server, not with the object.** An application reaches
its own configuration only once a server holds it, so the vertex is built at
startup out of what the recipe wrote under this front's code. There is ONE way to
build it, and the tests come through the same door as production.
``commander_class`` is a class attribute and not a kwarg: a Python type does not
travel in a recipe, and whoever wants another pool subclasses this front, which is
what the recipe already names.

**A pool belongs to the application that owns it.** The chain is server →
applications → this front → its commander → its groups → their workers, and the
recipe says it in that shape: the pool's words are this class's own grammar and
are written under ``applications.<code>.commander``. Several fronts on one server
are legitimate, each with its own pool. ``memory_max_percent`` stays a share of
the MACHINE, so apportioning it between two pools is the installation's own
business; an installation that over-declares is caught by the machine's alarm
line, past which nothing grows.

**Serving is a two-stage demux**, transcribed from the front it stands beside.
Stage 1 reads the FIRST segment of the (already mount-relative) path: not one of
``internal_roots`` — the app's own first-level roots — and the path belongs to the
hosted site. Stage 2 resolves the FULL path in the app's own router: the node
exists, so the request is served natively; a structural miss under a claimed root
belongs to the site after all and falls through. ``resolves_natively`` asks the
router WITHOUT auth filters, so a route that exists but would be denied still
answers its own 403 natively and never leaks the site behind it.

**The forward is one line.** Everything the pool does — the identity, the wait of
a user between two homes, the placement, the wire — happens inside
``SpaCommander.serve_request``. This front never names a group, a worker or a
wire, and keeps no state of its own: the cookie it mints is the only thing it
decides, and it decides it once per request.

**What comes back out.** The site's own answer, rebuilt from the reply. A refusal
— nobody could take this user, or he stayed between two homes longer than this
front is willing to wait — is a polite **503** carrying the ``Retry-After`` the
vertex composed, because only the vertex knows when the machine will have decided
again. A failure — the site broke inside a healthy process, or the wire is gone —
is a **502**: the site is this gateway's upstream and its breakage is not the
client's fault. Both answer with a GENERIC line: the real text is written to the
log, where the sysop looks for it, and never handed to a browser, because an
exception's text carries the inside of the house.
"""

from __future__ import annotations

import base64
import logging
import uuid
from typing import TYPE_CHECKING, Any

from genro_bag import BagResolver
from genro_builders.builder import element

from ..application import ApplicationGrammar
from ..middleware.base import cookie_value
from ..response import Response
from ..routed_application import RoutedApplication
from ..spa.orchestration import AssignmentRefused, SiteFailedRequest, SpaCommander

if TYPE_CHECKING:
    from ..types import Receive, Scope, Send

#: The connection cookie, legacy name and legacy attributes.
STICKY_CID_COOKIE = "sticky_cid"

#: How long a request may spend, in total, waiting for a user who is between two
#: homes. It is NOT derived from the beat: a move is an evict and an install,
#: milliseconds when things are well, and past a few seconds something is wrong
#: and the polite refusal is the honest answer.
REQUEST_HOLD_MAX_SECONDS = 5.0

#: What the two refusals say out loud. The inside of the house — which user, which
#: worker, what the site raised — goes to the log and not through the wire.
ERR_503_TEXT = "server busy"
ERR_502_TEXT = "the site could not answer this request"


class SpaApplicationGrammarNew(ApplicationGrammar):
    """The words this front adds to a recipe: its pool, and the groups under it.

    They live HERE and not in the site dialect because a pool belongs to the
    application that owns it: the chain is server → applications → this front →
    its commander → its groups → their workers. A recipe writes them under
    ``applications.<code>.commander``, which is the subtree this application
    reads back through its own door.
    """

    @element(parent_tags="commander", sub_tags="group", collection_key="name")
    def groups(self, default: str = None) -> None:
        """Collection of worker groups, each labelled by its ``name`` — stable paths
        ``applications.<code>.commander.groups.<name>``. A group is the workers built from ONE grammar:
        the same child, the same policies.

        The optional ``default`` ELECTS the group that receives whoever arrives
        with no past; omitted, the first group declared is the one. Unlike
        ``applications.default``, which is a redirect destination and elects
        nothing, this one decides where a newcomer is born."""

    @element(parent_tags="groups", sub_tags="")
    def group(
        self,
        name: str = None,
        memory_max_percent: float | BagResolver = None,
        worker_max_number: int | BagResolver = None,
        worker_memory_max_percent: float | BagResolver = None,
        occupancy_max_percent: float | BagResolver = None,
        restart_occupancy_max_percent: float | BagResolver = None,
        reception_reserved_percent: float | BagResolver = None,
        new_user_occupancy_percent: float | BagResolver = None,
        newcomer_reserve_count: int | BagResolver = None,
        user_idle_freeze_minutes: float | BagResolver = None,
        entry_module: str = None,
        executable: str | BagResolver = None,
        worker_class: str = None,
        main_threadpool_size: int | BagResolver = None,
        aux_threadpool_size: int | BagResolver = None,
        worker_kwargs: dict = None,
    ) -> None:
        """One group of workers: its own policies, and the identity of its child.

        ``name`` is the collection key and names the group's workers too
        (``<name>_0001``), so it is short — a worker's name is its socket's.

        **Nothing here says how many workers there are.** The group brings its
        reception into being at boot and then grows on demand and shrinks by
        waste, so the count is a reading and never a setting —
        ``worker_max_number`` included: it says how many workers the quota is
        SIZED FOR (the per-worker ceiling becomes quota / that number, 6 when
        nothing is declared), and caps nothing. It replaces the bridge-era
        RAM-share-over-workers derivation with one intuitive count of slots;
        an explicit ``worker_memory_max_percent`` wins over it.

        The POLICIES: ``memory_max_percent`` is this group's share of the
        server's concession and ``worker_memory_max_percent`` what ONE worker may
        hold of that share (the same word one rung down — the cascade is machine,
        concession, quota, worker); ``occupancy_max_percent`` is how full a worker
        gets before it stops admitting and ``restart_occupancy_max_percent`` where
        a process is replaced instead of kept; ``reception_reserved_percent`` is
        what the reception keeps free for the trade only it has;
        ``new_user_occupancy_percent`` is what a user nobody has ever measured is
        expected to cost, and ``newcomer_reserve_count`` how many of that size
        must always find room — the group grows at its own round before anybody
        is refused. ``user_idle_freeze_minutes`` is the silence past which a
        worker parks a user in the freezer.

        The IDENTITY of the child: ``entry_module`` (what ``python -m`` runs),
        ``executable`` (the interpreter — a group is how two versions of a site
        live side by side), ``worker_class`` (the ``module:Class`` the child
        loads), the two thread pool sizes, and ``worker_kwargs``, the grammar that
        class is built with. The two paths are the installation's and are declared
        once, on ``commander``.
        """

    @element(sub_tags="groups[0:1]", node_label="commander")
    def commander(
        self,
        frozen_users_path: str | BagResolver = None,
        instance_dir: str | BagResolver = None,
        memory_max_percent: float | BagResolver = None,
        machine_memory_alarm_percent: float | BagResolver = None,
        orchestration_log_path: str | BagResolver = None,
        orchestration_log_max_bytes: int | BagResolver = None,
        orchestration_log_backup_count: int | BagResolver = None,
        user_expiry_hours: float | BagResolver = None,
        guest_expiry_hours: float | BagResolver = None,
    ) -> None:
        """The SPA pool: the vertex's own policies, and the groups under it.

        The two PATHS of the installation, declared once here and shared by every
        group: ``frozen_users_path`` is the freezer root — the vertex reads what a
        worker wrote there, so it is one root for the whole machine — and
        ``instance_dir`` holds the sockets.

        ``memory_max_percent`` is what this server may hold OF THE MACHINE (the
        concession; omitted, all of it), and every percentage below is a share of
        it. ``machine_memory_alarm_percent`` is the health line of the whole
        machine, past which nothing grows. The freezer's own storage answers to no
        key: under a tenth free the log says so and the machine asks for more.

        ``orchestration_log_path`` (+ ``_max_bytes`` / ``_backup_count``) is the
        file every order lands on — who decided, what, on whom, with which numbers
        and how it ended; omitted, the rows stay on the logger.

        ``user_expiry_hours`` / ``guest_expiry_hours`` are the ages a FROZEN user
        is kept for before the machine forgets him whole. A guest is shorter: he
        is a browser, not a person the machine knows.

        Technical times — the beat, the patience of a departure, the cadences —
        are module constants and not grammar: an installation tunes policies, not
        clocks.
        """


class SpaApplicationNew(RoutedApplication):
    """A single-page-application front backed by the new user-sticky pool."""

    #: The words this front adds to a recipe, read back under its own code.
    grammar = SpaApplicationGrammarNew

    #: The pool this front builds. A subclass names another one — a vertex that
    #: can grow its own machine, say — and the recipe names the subclass.
    commander_class: type[SpaCommander] = SpaCommander

    def __init__(self, **kwargs: Any) -> None:
        self._commander: SpaCommander | None = None
        self._logger = logging.getLogger(__name__)
        super().__init__(**kwargs)

    @property
    def commander(self) -> SpaCommander:
        """The pool this front owns.

        Raises:
            RuntimeError: it is not built yet — the vertex is born at startup,
                out of a configuration that only a mounted application can read.
        """
        if self._commander is None:
            raise RuntimeError(
                f"{type(self).__name__} has no pool yet: it is built when the server starts"
            )
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

        Resolution runs with NO auth filters, so the answer is purely "does this
        node exist?". Only a genuine ``not_found`` is a miss; an existing node a
        filter would deny still answers True and stays native.
        """
        return bool(self.route.node(path).error != "not_found")

    async def on_startup(self) -> None:
        """Build the pool out of the recipe and bring it up, once the server is there.

        The vertex is born HERE and not in the constructor: its words live under
        ``applications.<code>.commander``, and an application reaches its own
        subtree only once a server has it.

        Acts on this application — the vertex is born here — and, through
        ``SpaCommander.start``, on the machine: the base group's reception is
        launched and awaited, then the beat starts. A reception that would not
        start leaves its group broken and the front serves polite refusals until
        the group's own round brings one up: a process that fails to start can be
        a passing thing, and the machine knows how to heal it.
        """
        handler = self.server.config
        self._commander = self.commander_class(
            **handler.commander_kwargs(self.code), groups=handler.group_kwargs(self.code)
        )
        await self.commander.start()

    async def on_shutdown(self) -> None:
        """Take the pool down with the server."""
        if self._commander is not None:
            await self.commander.stop()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Demultiplex: the app's own router, else the hosted site."""
        path = str(scope.get("path", "/"))
        first_segment = path.strip("/").split("/")[0]
        if first_segment in self.internal_roots and self.resolves_natively(path):
            await super().__call__(scope, receive, send)
        else:
            await self.forward_request(scope, receive, send)

    async def forward_request(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve a site path through the pool: pack, hand over, translate, answer.

        The cookie is read ONCE here and the fact travels down: the packing is
        told whether the request carried one instead of scanning the headers for
        it again. A request that carried none is answered with the cookie this
        front just minted; one that carried it needs nothing.
        """
        carried = self.request_cid(scope)
        cid = carried or uuid.uuid4().hex
        http = await self.pack_http(scope, receive, cid, carried)
        try:
            reply = await self.commander.serve_request(
                cid, http, hold_timeout=REQUEST_HOLD_MAX_SECONDS
            )
        except AssignmentRefused as refusal:
            self._logger.warning("Front %s: %s", self.code, refusal)
            response = self.busy_response(refusal, cid, carried is None)
        except (SiteFailedRequest, ConnectionError) as failure:
            self._logger.error("Front %s: %s", self.code, failure)
            response = self.gateway_response(cid, carried is None)
        else:
            response = self.build_response(reply, cid, carried is None)
        await response(scope, receive, send)

    def busy_response(
        self, refusal: AssignmentRefused, cid: str, issue_cookie: bool
    ) -> Response:
        """The polite 503: come back when the machine will have decided again."""
        headers = [("content-type", "text/plain; charset=utf-8")]
        if refusal.retry_after is not None:
            headers.append(("retry-after", str(int(refusal.retry_after))))
        response = Response(content=ERR_503_TEXT, status_code=503, headers=headers)
        return self.stamp_cookie(response, cid, issue_cookie)

    def gateway_response(self, cid: str, issue_cookie: bool) -> Response:
        """The 502 of an upstream that broke: what broke is said in the log alone."""
        response = Response(
            content=ERR_502_TEXT,
            status_code=502,
            headers=[("content-type", "text/plain; charset=utf-8")],
        )
        return self.stamp_cookie(response, cid, issue_cookie)

    def build_response(self, reply: dict[str, Any], cid: str, issue_cookie: bool) -> Response:
        """The outer response, rebuilt from the site's own answer."""
        result = reply["result"]
        response = Response(
            content=base64.b64decode(result.get("body") or ""),
            status_code=int(result.get("status", 200)),
            headers=[(str(name), str(value)) for name, value in result.get("headers") or []],
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
        """Pack the ASGI request into the JSON-safe ``http`` form the child reads.

        The cid travels twice: as its own key, which is what the child routes the
        row on, and inside the forwarded ``cookie`` header, because the hosted
        site must see the connection this request already belongs to even when the
        browser does not carry it yet.
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
            "cid": cid,
        }

    def pack_headers(self, scope: Scope, cid: str, carried: str | None) -> list[list[str]]:
        """The request headers as a pair-list, with ``sticky_cid`` guaranteed present.

        A minted cid JOINS the request's own ``cookie`` header (``"; "``, RFC
        6265): a second ``cookie`` pair would be comma-joined by the PEP 3333
        reassembly on the serving side, mangling every cookie in it.
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
