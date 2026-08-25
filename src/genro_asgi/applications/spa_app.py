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

"""The mountable SPA front: one door, and no state at all.

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

**Serving is a two-stage demux.**
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
wire, and keeps no state of its own. It mints nothing either: the cookie carries
the hosted site's own connection id, read off the answer and written back on the
way out, so the identity the browser holds and the identity the site keeps are
one and the same.

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
from typing import TYPE_CHECKING, Any

from genro_bag import BagResolver
from genro_builders.builder import element

from ..application import ApplicationGrammar
from ..middleware.base import cookie_value
from ..response import Response
from ..routed_application import RoutedApplication
from ..server import QUITTING, REFUSED_RETRY_AFTER_SECONDS, RUNNING
from ..spa.orchestration import AssignmentRefused, SiteFailedRequest, SpaCommander

if TYPE_CHECKING:
    from ..types import Receive, Scope, Send

#: The routing cookie. Its value is the hosted site's OWN connection id, never a
#: number of ours: one identity space, so the chain from the cookie to the worker
#: translates nothing.
SPA_CONNECTION_ID_COOKIE = "spa_connection_id"

#: How long that cookie lives. The same 24 hours the site gives its own connection
#: cookie (``CONNECTION_TIMEOUT * 24``, gnrwebpage_proxy/connection.py): ours must
#: not die first, or a browser the site still recognises would come back with no
#: connection named and be routed anonymous for the rest of the day.
CONNECTION_COOKIE_MAX_AGE = 24 * 3600

#: How long a request may spend, in total, waiting for a user who is between two
#: homes. It is NOT derived from the beat: a move is an evict and an install,
#: milliseconds when things are well, and past a few seconds something is wrong
#: and the polite refusal is the honest answer.
REQUEST_HOLD_MAX_SECONDS = 5.0

#: What the two refusals say out loud. The inside of the house — which user, which
#: worker, what the site raised — goes to the log and not through the wire.
ERR_503_TEXT = "server busy"
ERR_502_TEXT = "the site could not answer this request"


class SpaApplicationGrammar(ApplicationGrammar):
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
        engine_factory: str = None,
        engine_kwargs: dict = None,
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

        The BIRTH of the child: ``engine_factory`` is the ``module:Class`` of the
        class that builds the one expensive thing all this group's workers share,
        and ``engine_kwargs`` what that class is built with. Declared, the group
        runs a template process that builds it once and forks every worker out of
        it, so the cost is paid once instead of once per worker. Omitted, the group
        spawns its workers the ordinary way and has no template at all.
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


class SpaApplication(RoutedApplication):
    """A single-page-application front backed by the new user-sticky pool."""

    #: The words this front adds to a recipe, read back under its own code.
    grammar = SpaApplicationGrammar

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
        """Take the pool down with the server: with a photo, or dry.

        A server that is QUITTING gets the soft quit — every user parked in the
        reboot directory and the vertex's own item beside them. Any other way
        out is dry, which is what every start that is not the deliberate liturgy
        expects to find (F2).
        """
        if self._commander is None:
            return
        if self.server.state == QUITTING:
            await self.commander.quit()
        else:
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

        The cookie is read ONCE here and travels down as it came — None included,
        which is a browser the site has never named. Nothing is minted: the
        identity is the site's to give, and it gives it while serving. What comes
        back names the connection the request settled on, and that is what the
        cookie is written with.
        """
        carried = self.request_cid(scope)
        http = await self.pack_http(scope, receive, carried)
        try:
            reply = await self.commander.serve_request(
                carried, http, hold_timeout=REQUEST_HOLD_MAX_SECONDS
            )
        except AssignmentRefused as refusal:
            self._logger.warning("Front %s: %s", self.code, refusal)
            response = self.busy_response(refusal)
        except ConnectionError as gone:
            self._logger.warning("Front %s: %s", self.code, gone)
            response = self.wire_lost_response(gone)
        except SiteFailedRequest as failure:
            self._logger.error("Front %s: %s", self.code, failure)
            response = self.gateway_response()
        else:
            response = self.build_response(reply, carried)
        await response(scope, receive, send)

    def busy_response(self, refusal: AssignmentRefused) -> Response:
        """The polite 503: come back when the machine will have decided again.

        No cookie goes out with it: the site never served this request, so there
        is no connection to name — and a refusal must not overwrite the one the
        browser already holds.
        """
        headers = [("content-type", "text/plain; charset=utf-8")]
        if refusal.retry_after is not None:
            headers.append(("retry-after", str(int(refusal.retry_after))))
        return Response(content=ERR_503_TEXT, status_code=503, headers=headers)

    def wire_lost_response(self, gone: ConnectionError) -> Response:
        """What a dead wire means depends on why the process on the other end left.

        A server that is quitting killed that wire on purpose, so the answer is
        the polite 503 a refusal gets — the browser is told to come back, not
        that something upstream broke. A wire that died while the server was
        running IS a breakage, and reads 502.
        """
        if self.server.state == RUNNING:
            return self.gateway_response()
        return Response(
            content=ERR_503_TEXT,
            status_code=503,
            headers=[
                ("content-type", "text/plain; charset=utf-8"),
                ("retry-after", str(REFUSED_RETRY_AFTER_SECONDS)),
            ],
        )

    def gateway_response(self) -> Response:
        """The 502 of an upstream that broke: what broke is said in the log alone."""
        return Response(
            content=ERR_502_TEXT,
            status_code=502,
            headers=[("content-type", "text/plain; charset=utf-8")],
        )

    def build_response(self, reply: dict[str, Any], carried: str | None) -> Response:
        """The outer response, rebuilt from the site's own answer.

        The cookie is written when the connection the site settled on is not the
        one the browser sent: a first visit, and the replacement the site makes
        whenever the connection its own cookie names does not validate. A request
        that reused the connection it arrived with names none, and nothing is
        written.
        """
        result = reply["result"]
        response = Response(
            content=base64.b64decode(result.get("body") or ""),
            status_code=int(result.get("status", 200)),
            headers=[(str(name), str(value)) for name, value in result.get("headers") or []],
        )
        settled = result.get("connection_id")
        if settled is not None and settled != carried:
            response.set_cookie(
                SPA_CONNECTION_ID_COOKIE,
                settled,
                max_age=CONNECTION_COOKIE_MAX_AGE,
                path="/",
                httponly=True,
                samesite="lax",
            )
        return response

    def request_cid(self, scope: Scope) -> str | None:
        """The connection this request carries, or ``None`` when it carries none."""
        return cookie_value(scope, SPA_CONNECTION_ID_COOKIE)

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
        self, scope: Scope, receive: Receive, cid: str | None
    ) -> dict[str, Any]:
        """Pack the ASGI request into the JSON-safe ``http`` form the child reads.

        The headers are forwarded as they came: our cookie is ours to route on
        and the hosted site has no use for it — it reads its own, and the value
        in both is its own connection id anyway.
        """
        query_string = scope.get("query_string") or b""
        client = scope.get("client") or None
        return {
            "method": str(scope.get("method", "GET")),
            "path": str(scope.get("path", "/")),
            "query_string": query_string.decode("latin-1"),
            "headers": [
                [name.decode("latin-1"), value.decode("latin-1")]
                for name, value in scope.get("headers") or []
            ],
            "body": base64.b64encode(await self.read_body(receive)).decode("ascii"),
            "client": list(client) if client else [],
            "scheme": str(scope.get("scheme", "http")),
            "cid": cid,
        }
