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

"""The UserSticky worker runtime: registers, ops, outbox, the two signal paths.

A worker is the execution half of the UserSticky pair. It is NOT an ASGI
application — a child speaks only the channel (design §3.1) — so this is a
plain object that owns:

- ``registry`` — its :class:`RegisterRegistry`; ``user_items`` is the register
  of the users this worker holds. Contents live here and nowhere else: the
  commander keeps keys and locations only.
- ``outbox`` — the FIFO the async sender drains: every ascending message —
  exchange traffic, dbevent deposits, global-store writes — rides it up to
  the commander.
- ``last_seq`` — the per-worker monotonic sequence stamped on every shaped
  event, assigned under ``dispatch_lock`` so seq order IS mutation order.
- ``pool`` — a :class:`WorkPool` whose parent is the worker itself: a sync op
  handler runs off the loop, an async one stays on it.
- ``http_pool`` — a second :class:`WorkPool`, the WSGI seam's own: site
  requests are long and synchronous, and share no threads with the ops.
- ``channel`` — the member face of the wire (a :class:`WorkerChannelClient`
  over a socket, or a :class:`LocalChannel` in the single role): the same API
  either way, injected by whoever builds the worker.

**One envelope per CALL, three sub-envelopes.** ``service_call`` opens two sinks
— instance ContextVars holding fresh lists — for the CALL it is answering, and
``send_reply`` ships them beside the browser's own answer. The REPLY therefore
carries three classes: the answer to the caller (``result``/``error`` plus the
drain under ``DELIVERY_KEYS``), the SYNCHRONOUS class (``events``) and the TASK
class (``tasks``). Empty classes carry no key.

``offer_event`` appends to whichever causal sink its context sees (a sync
handler runs on a pool thread with the context copied, so it appends to the same
list): a REPLY reports the lifecycle the answered call CAUSED, nothing else. The
commander folds that class in the caller's own coroutine BEFORE reading the
result, so the routing picture is already updated when the response is released.
Each CALL is SERVED on its own task — ``create_task`` copies the context, so the
sinks of a CALL in flight are its own lists and two CALLs never mix; a lifecycle
op outside any CALL is impossible and says so.

The task class is the ascending work the CALL produced for OTHER workers' pages:
``route_datachange``'s tier 3, shaped exactly as it would ride the outbox. The
commander runs one task per command AFTER releasing the caller, so the browser
never waits on a deposit meant for somebody else.

**The outbox is the async rail of the out-of-request producers.** ``Outbox``,
``notify_sender`` and ``sender_loop`` are the transport of the cross-worker
traffic born OUTSIDE a CALL (design D4): a datachange whose target is not here,
produced by a background task, rides them up to the commander as an EVENT with
its per-seq ack. Born inside a CALL, that same command rides the REPLY instead.
The lifecycle comes through here from ONE producer only, for the same reason:
the expiry sweep, which decides its drops on this worker's own clock with no
CALL to answer. Every other lifecycle event rides the REPLY that caused it.

**Expiry is stamped by the server and swept on the server's clock.** Every row
of the chain is born with ``last_refresh_ts``, and a page-addressed CALL — the
page's own sign of life — re-stamps the page, its connection and its user
inside the pull trip (``refresh_chain``), always with ``time.time()`` and never
with a value the client supplied. ``sweep_expired`` then drops what has been
idle past ``PAGE_MAX_AGE``/``GUEST_MAX_AGE``/``CONNECTION_MAX_AGE``, announcing
each drop on the outbox. It is DISARMED unless ``sweep_interval`` is given:
until the browser rail carries a presence signal, a quiet page and a dead one
look alike from here.

**The login never pushes** (ratified 2026-08-12). ``change_connection_user``
re-labels the CONNECTION onto the logged-in user — a mutation, never a re-key:
keys, live stores and collectors survive it, with ONE declared exception: the
anonymous user entry claiming its first real identity is transferred whole onto
the new key, store included. A user this worker already hosts is joined: the
connection links to the resident entry. Either way the slice STAYS here and
only the event travels, so the request that carried the login keeps finding
its pages on this worker to the end. Where the user belongs is the commander's
question, answered at the fold: a user that belongs elsewhere leaves later,
through the ordinary commanded move.

**The commander can also ORDER the departure.** ``evict_user`` packages the same
slice on demand and answers with it: no event, because the surface itself asked
— it is the reply that tells it. That is the op a rebalance uses, and the op the
commander walks its whole map with when it dumps the register to disk on the way
down.

**The move carries the whole slice, and the rebirth has one order.** The parcel
is the user entry with its store, every CONNECTION of that user, and every page:
the page store, both subscription sets, and everything that was pending for it,
drained on the way out (``evict_pages``). It is sealed Python-to-Python —
pickle, base64 inside the JSON envelope — because nobody reads it en route. At
the destination the user lands first, then the connections, then
``install_page`` rebuilds each page in the only order that works: the Bags
arrive hydrated with the unpickling, the collectors attach ONLY THEN (earlier
and the hydration itself would be captured as fresh changes), the subscriptions
live again, and the pendings are re-deposited last with ``append`` — producer
``change_ts`` kept, local ``change_idx`` fresh, so the destination drains them
in the order they left. That is what "the room is ready" means now, and
``add_user`` returns only once it is.

**The rebirth JOINS a resident.** A user already living at the destination is
never re-born: the resident entry and its live store win, the blob's copy of
them is dropped on the floor, and only the arriving connections and pages are
installed — onto the resident store. That is how a user comes to hold a second
connection.

**Operational signals are ANSWERED, never pushed.** ``occupancy`` is an async
op like any other: the commander probes it and the worker replies with the
counters its registers can answer. Because the answer comes from the loop, one
exchange carries both readings — the data, and the proof that this worker is
still alive to produce it. The worker owns no clock for it.

**Op vocabulary.** ``LIFECYCLE_OPS``/``STORE_OPS``/``POST_OPS``/
``EXCHANGE_OPS`` are transcribed whole from the legacy worker: they are the
reserved protocol names, and all four families are live — the lifecycle ops
mutate the registers and shape the events a REPLY carries up, the store ops
ascend to the master, the POST ops feed the dbevents rail, the exchange ops
ride the three-tier switch. The install primitives are operational (they
mutate on the commander's own order, so they shape no event);
``drop_pages`` and ``drop_connections`` remain reserved names with no
handler.

**The live stores have one drain point.** ``collect_page`` is where everything
pending for a page leaves the worker: its own store collector and its
``user_view`` merged by ``change_ts``, plus the dbevents in their own key —
three species, never conflated. ``apply_forwarded`` is the other half: a
change born on another worker becomes a real local write carrying the
producer's instant as ``_original_ts``, while the local ``change_ts`` stays
the apply time so ordering remains local.

**The drain rides the REPLY: delivery is PULL.** A CALL whose kwargs carry a
``page_id`` is that page's request/response cycle, and ``send_reply`` merges
``wire_delivery`` into its envelope under ``DELIVERY_KEYS`` — each species
TYTX-encoded, because a change carries a node value and a datetime that JSON
cannot. The drain takes ``dispatch_lock``, so ``send_reply`` hands it to the
pool like every other lock-taking work. Nothing is pushed: a change for a page
that never calls waits in its collector. The op outcome does not gate the
drain, and a CALL addressing no page carries neither key.

**The addressed write has three tiers, and one switch.** ``set_datachange``,
``reset_datachanges`` and ``drop_datachanges`` all address a target that may or
may not be here, and ``route_datachange`` is the switch: a target this worker
holds is applied at once (tier 2 — no channel traffic), anything else ascends
to the commander — on the answered CALL's task class, or on the outbox when no
CALL is being served — which resolves it and pushes it back down as a
``DATACHANGE_IN_PATH`` batch (tier 3). Tier 1 needs no op at all: a page writing
its own store writes the Bag. A filtered broadcast always ascends — the surface
that knows every page is up there.

**STATE applies as a write, SIGNAL applies as a deposit.** ``kind`` says which:
``page_store``/``user_store``/``connection_store`` are state, so they land
through ``apply_forwarded`` (a real Bag write, ``_original_ts`` carried) — the
connection store is server-side only, so nothing of it is ever delivered to a
browser, it is simply the third register a store address can name; ``page`` is a
signal (``setInClientData`` semantics), so it lands through ``append`` on the
target page's collector — no Bag write, no residue, the producer's
``change_ts`` preserved by ``append`` itself. The change travels TYTX-encoded
from origin to destination, decoded only where it is applied: the commander
routes on the readable header alone and never opens it.

**dbevents are their own species, on their own pipe.** ``subscribeTable`` and
``notifyDbEvents`` are the POST ops, and nothing they carry is ever dressed as a
datachange: a subscription mutates this worker's ``SubscriptionIndex`` (the
local fan-out surface) AND ascends, so the commander can reach the OTHER
workers' subscribers; a notify fans out LOCALLY first — the co-located pages are
served with zero channel traffic — and then ascends, and the commander excludes
this very worker from its own fan-out (§2.4 origin exclusion) so no page is
served twice. The descending pipe is ``DBEVENTS_IN_PATH``, distinct from the
exchange rail: a deposit is not a change, and the two never share a batch. The
deposit itself is shaped ONCE, by the origin worker, so every page — local or
remote — reads the same ``ts``; it is JSON by construction, so this rail needs
no encoding at all. A page that left while the batch was on the wire loses its
deposit: a dbevent is a signal, and there is no retry queue.

**The table cache is invalidated by the same dbevent.** A page store may hold
values cached from a table: the writer marks the node with a ``_caching_table``
attribute, and a per-page observer subscribed to that store records the pair in
``cached_tables`` (``table -> page_id -> paths``). The observer is INDEPENDENT
of the page collector's prefix filter — the daemon records the cached path
before and outside its own prefix match — and it is the worker's, not the
registry's: the worker attaches it when a page is born or installed and
unsubscribes it when the page leaves. A dbevent on a table pops its entry and
writes ``None`` on every cached path, a REAL store write, so the page's
filtered collector captures the invalidation exactly when that page subscribed
the path. It runs on both rails, the ``notifyDbEvents`` origin and the
descending batch, and NEVER under ``local_only``: a hidden transaction belongs
to its own page and invalidates nothing.

**The global store is read here and written above.** ``global_store`` is this
worker's REPLICA Bag: local reads, zero round-trip, read-only by convention
because the single writer is the commander. The ``store_set``/``store_del`` ops
therefore write nothing locally — they ascend, and the write comes back down as
a ``GLOBAL_CHANGES_PATH`` batch like every other worker's. ``global_store_lock``
is the read-modify-write form: the request ascends as ``store_lock``, the grant
comes back carrying the master's content, the holder mutates a WORKING COPY, and
the drained changes travel back with ``store_unlock``. The descending global
frames are applied INLINE in ``handle_frame``, never on a task: the snapshot must
precede the changes and the receive loop is the only thing that keeps them in
order.

**CALL forms.** ``data`` is ``{identity, kwargs}`` — ``identity`` is the
sticky key and reaches the handler as its first argument. The
``{identity, http: {...}}`` form is the service rail for the old code:
``serve_http`` hands its facts to a :class:`~.environ.WsgiSeam`, which
synthesizes the PEP 3333 environ and invokes ``wsgi_app`` in-process on a
thread of ``http_pool`` — the SECOND pool, dedicated to the seam so a burst of
site requests cannot starve the op handlers — WSGI as an adapter, never as a
transport. The CALL's ``identity`` reaches the site as ``genro.identity``.
``wsgi_app`` is the consumer seam: ``None`` on this class, assigned by the
worker subclass that hosts a WSGI site, and while it is ``None`` the http form
is answered with an explicit error REPLY.
"""

from __future__ import annotations

import asyncio
import base64
import ctypes
import functools
import logging
import pickle
import resource
import threading
import time
from contextvars import ContextVar
from typing import Any, Callable

from genro_bag import Bag
from genro_routes import RoutingClass, route
from genro_tytx import from_tytx, to_tytx

from ..channel.client import ChannelClient
from ..channel.frame import Frame
from ..channel.hub import CALL_METHOD, EVENT_METHOD, REPLY_METHOD
from ..pool import WorkPool
from .environ import WsgiSeam
from .global_store import (
    GLOBAL_CHANGES_PATH,
    GLOBAL_GRANT_PATH,
    GLOBAL_SNAPSHOT_PATH,
    CapturingGlobalStore,
    GlobalStore,
    GlobalStoreLease,
)
from .register import Register
from .register_registry import GUEST_PREFIX, RegisterRegistry
from .subscription_index import SubscriptionIndex

__all__ = [
    "DATACHANGE_IN_PATH",
    "DBEVENTS_IN_PATH",
    "DELIVERY_KEYS",
    "EXCHANGE_OPS",
    "LIFECYCLE_OPS",
    "LIVE_ROW_FIELDS",
    "MOVE_CONNECTION_REBUILT_FIELDS",
    "MOVE_REBUILT_FIELDS",
    "MOVE_REPLAYED_KEYS",
    "OP_PATH_PREFIX",
    "POST_OPS",
    "SIGNAL_KIND",
    "STATE_KINDS",
    "STORE_OPS",
    "Outbox",
    "UserStickyWorker",
    "WorkerChannelClient",
]

# The register commands that are lifecycle (they mutate the routing-level picture and
# must reach it); everything else is operational and stays worker-local.
LIFECYCLE_OPS = frozenset(
    {
        "new_connection",
        "change_connection_user",
        "new_user",
        "new_page",
        "drop_page",
        "drop_pages",
        "drop_connection",
        "drop_connections",
        "drop_user",
    }
)

# The ascending-operational commands: everything the master global store must
# hear. The two writes are the 2a reserved names; the lock pair is 2b's ONE
# vocabulary addition, and it travels the same ascending rail for the same reason
# — the master is up there and only the commander writes it.
STORE_OPS = frozenset({"store_set", "store_del", "store_lock", "store_unlock"})

# The POST commands: table subscriptions and db-event notifications. Reserved names —
# the subscription surfaces arrive with the pages (2b).
POST_OPS = frozenset({"subscribeTable", "notifyDbEvents"})

# The datachange EXCHANGE commands: applicative writes toward a page (or a user's
# store). Each carries its own address and rides the same three-tier switch.
EXCHANGE_OPS = frozenset({"set_datachange", "reset_datachanges", "drop_datachanges"})

#: Routing prefix of an op CALL/EVENT path: ``/op/new_user`` carries op ``new_user``.
OP_PATH_PREFIX = "/op/"

#: The internal rail the commander pushes a resolved exchange batch down: ONE
#: EVENT per destination worker, whatever the batch holds (legacy name).
DATACHANGE_IN_PATH = "/datachange_in"

#: The dbevents rail, descending — the same batching mechanics as the exchange
#: one and a DISTINCT pipe: a deposit is not a change and never shares a batch
#: with one.
DBEVENTS_IN_PATH = "/dbevents_in"

#: The address kinds that name a STORE: the change applies as a real Bag write
#: through ``apply_forwarded``, carrying the producer's instant as
#: ``_original_ts``.
STATE_KINDS = frozenset({"page_store", "user_store", "connection_store"})

#: The address kind that names a page itself: the change is a SIGNAL and applies
#: as a deposit on that page's collector — no Bag write, no residue.
SIGNAL_KIND = "page"

#: The REPLY keys of the pull delivery, one per species — a dbevent is never
#: dressed as a datachange. The commander passes them through untouched.
DELIVERY_KEYS = ("datachanges", "dbevents")

# The row fields that never leave this process: the live local objects — the
# stores and the collectors on them, the worker's own memory — plus the two
# structural edge sets of the ownership tree, which the install rebuilds from
# the rows it lands. An op answers with the wire-safe view of a row, and a
# moving user's store is serialized on purpose by the move packaging, never by
# an op result.
LIVE_ROW_FIELDS = frozenset({"store", "collector", "user_view", "connections", "pages"})

# The page-row fields the rebirth builds itself, so a move package never carries
# them: the two collectors (objects bound to THIS process's Bags), the
# ``dbevents`` container a row is born with, and the reserved key. Everything
# else in a packaged row is a value handed straight back to ``new_page``.
MOVE_REBUILT_FIELDS = frozenset({"register_item_id", "collector", "user_view", "dbevents"})

# The packaged keys the rebirth replays BY HAND, in order, once the row exists:
# ``new_page`` seeds each of them itself and would refuse them as keywords.
MOVE_REPLAYED_KEYS = frozenset(
    {
        "subscribed_paths",
        "store_subscriptions",
        "table_subscriptions",
        "pending_datachanges",
        "pending_dbevents",
    }
)

# The connection-row fields the rebirth builds itself: the reserved key, the
# user the destination re-creates the row under, and the ``pages`` edge set the
# arriving pages fill in as they land. Everything else travels verbatim — the
# row's live ``store`` included, pickled whole inside the blob and handed back
# to ``new_connection``, which honours a supplied store.
MOVE_CONNECTION_REBUILT_FIELDS = frozenset({"register_item_id", "user", "pages"})

# The idle ages, in seconds, the expiry sweep measures ``last_refresh_ts``
# against — the daemon's own defaults (siteregister.py:42 and :564-566).
# PROVISIONAL: the daemon reads them per-group from the site configuration, and
# this transposition keeps them module-level until the configuration seam exists.
PAGE_MAX_AGE = 600
GUEST_MAX_AGE = 40
CONNECTION_MAX_AGE = 7200


class MallInfo2(ctypes.Structure):
    """The glibc ``mallinfo2()`` result: ten ``size_t`` fields, in order.

    A type declaration, not state: ctypes needs a class to set as ``restype``.
    ``fordblks`` — total free bytes held by the C heap — is the one field the
    worker's ``reusable_bytes()`` reads. The legacy ``mallinfo()`` is never
    used: its ``int`` fields overflow past 2 GB.
    """

    _fields_ = [
        ("arena", ctypes.c_size_t),
        ("ordblks", ctypes.c_size_t),
        ("smblks", ctypes.c_size_t),
        ("hblks", ctypes.c_size_t),
        ("hblkhd", ctypes.c_size_t),
        ("usmblks", ctypes.c_size_t),
        ("fsmblks", ctypes.c_size_t),
        ("uordblks", ctypes.c_size_t),
        ("fordblks", ctypes.c_size_t),
        ("keepcost", ctypes.c_size_t),
    ]


class Outbox:
    """FIFO of shaped ascending messages, acked per-seq by the drainer.

    Owned by the worker (semantic parent: ``self.worker``). Events arrive
    already shaped (they carry their per-worker ``seq``); the drainer acks the
    highest seq it shipped, and only then are those events dropped — so events
    queued while a batch is in flight are never lost. ``notify`` is the sender
    task's wakeup, called after each ``offer`` (``None`` until the worker
    attaches its channel). Thread-safe: events are born on pool threads, the
    drains run on the loop.
    """

    def __init__(self, worker: UserStickyWorker) -> None:
        self.worker = worker
        self.lock = threading.Lock()
        self.events: list[dict[str, Any]] = []
        self.acked_seq = 0
        self.notify: Callable[[], None] | None = None

    def offer(self, event: dict[str, Any]) -> None:
        """Queue one shaped event (it carries its seq), then wake the sender."""
        with self.lock:
            self.events.append(event)
        if self.notify is not None:
            self.notify()

    def drain(self, ack: int | None = None) -> list[dict[str, Any]]:
        """Ack what the drainer applied, then return a snapshot of what is pending.

        ``ack`` is the highest seq the drainer confirmed: events up to it are
        dropped; everything still pending (including events queued while the
        previous batch was in flight) is returned again — at-least-once.
        """
        with self.lock:
            if ack is not None and ack > self.acked_seq:
                self.acked_seq = ack
                self.events = [e for e in self.events if e.get("seq", 0) > ack]
            return list(self.events)

    def pending(self) -> int:
        """How many events are waiting to be drained."""
        with self.lock:
            return len(self.events)

    @property
    def ping_now(self) -> bool:
        """True when there is something to drain."""
        return self.pending() > 0


class WorkerChannelClient(ChannelClient):
    """The socket member face of a worker: ``ChannelClient`` plus ``send_frame``.

    A REPLY reuses the CALL's id, which ``send()`` cannot do — it mints a fresh
    one per frame. ``channel/client.py`` is ratified untouchable, so the one
    frame kind whose id is not the sender's to choose is added here, alongside
    the ``send_frame`` the ``LocalChannel`` member face already offers: the
    worker sees one endpoint API whichever wire it sits on.
    """

    async def send_frame(self, frame: Frame) -> str:
        """Send an already-built frame; returns its id."""
        if self._stream is None or not self.connected:
            raise ConnectionError("not connected")
        try:
            await self._stream.write(frame)
        except (BrokenPipeError, ConnectionResetError):
            self._logger.debug("send_frame: hub connection already closed")
        return frame.id


class UserStickyWorker(RoutingClass):
    """The execution unit: op handlers over its own registers, on the channel.

    Ops are ``@route`` methods dispatched by the CALL path's last segment, each
    receiving the sticky ``identity`` plus the CALL's ``kwargs``. A sync
    handler runs on ``pool``, a coroutine on the loop — the node's own nature
    picks the vehicle.
    """

    def __init__(
        self,
        name: str,
        *,
        channel: Any = None,
        max_threads: int | None = None,
        sweep_interval: float | None = None,
        page_max_age: float = PAGE_MAX_AGE,
        guest_max_age: float = GUEST_MAX_AGE,
        connection_max_age: float = CONNECTION_MAX_AGE,
    ) -> None:
        """Args:
        name: the worker's channel name (already typed, e.g. ``W:w1``).
        channel: the member face of the wire; ``attach_channel`` may set it later.
        max_threads: ``WorkPool`` size for the sync op handlers.
        sweep_interval: seconds between two expiry sweeps; ``None`` (the
            default) arms no sweep at all — see ``sweep_expired``.
        page_max_age: idle seconds a page survives the sweep (the daemon's
            default when not given).
        guest_max_age: idle seconds an anonymous page or connection survives.
        connection_max_age: idle seconds a logged connection survives.
        """
        self.name = name
        self.sweep_interval = sweep_interval
        self.page_max_age = page_max_age
        self.guest_max_age = guest_max_age
        self.connection_max_age = connection_max_age
        self.registry = self.build_registry()
        self.outbox = Outbox(self)
        self.pool = WorkPool(self, max_threads)
        # A SECOND pool, dedicated to the WSGI seam: a burst of site requests
        # runs long and synchronous, and must never starve the op handlers.
        self.http_pool = WorkPool(self, max_threads)
        # Reentrant: the subscription index takes this very lock, so an index
        # change and the row change it belongs to are ONE critical section even
        # though the op already holds it.
        self.dispatch_lock = threading.RLock()
        self.subscriptions = SubscriptionIndex(self.dispatch_lock)
        # The table cache index: table -> page_id -> the paths of that page's
        # store holding values cached from the table. Filled by the per-page
        # cache observer, emptied by an invalidation or by the page leaving.
        self.cached_tables: dict[str, dict[str, set[str]]] = {}
        # The global store as this worker sees it: a replica, read locally and
        # written only by what the commander pushes down.
        self.global_replica = GlobalStore()
        # The lock requests parked on their grant, by request id.
        self.global_grants: dict[str, asyncio.Future[Any]] = {}
        self.last_seq = 0
        # The CPU probe's previous reading: a fraction needs two ticks to exist.
        self.cpu_probe_ts: float | None = None
        self.cpu_probe_used: float | None = None
        # The glibc heap gauges, resolved ONCE: a missing symbol (macOS, musl,
        # glibc < 2.33) leaves the handle None and turns the feature off.
        self.libc_malloc_trim, self.libc_mallinfo2 = self.resolve_heap_symbols()
        self.logger = logging.getLogger(__name__)
        self.channel: Any = None
        # The consumer seam for the http CALL form: a WSGI callable assigned by
        # the subclass that hosts a WSGI site. None here — this class serves no
        # site of its own.
        self.wsgi_app: Callable[..., Any] | None = None
        # The causal sink: the events produced BY the CALL being answered in
        # this context. Instance-owned (never module level), so two CALLs in
        # flight fill two distinct lists.
        self._call_events: ContextVar[list[dict[str, Any]] | None] = ContextVar(
            "call_events", default=None
        )
        # The task sink: the commands the CALL produced for the commander to run
        # AFTER the caller is released. Same mechanics as the causal sink.
        self._call_tasks: ContextVar[list[dict[str, Any]] | None] = ContextVar(
            "call_tasks", default=None
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._outbox_ready = asyncio.Event()
        self._sender_task: asyncio.Task[None] | None = None
        self._sweep_task: asyncio.Task[None] | None = None
        # Strong refs to the CALLs being served: the loop keeps only weak ones.
        self._service_tasks: set[asyncio.Task[None]] = set()
        if channel is not None:
            self.attach_channel(channel)

    def build_registry(self) -> RegisterRegistry:
        """The registry factory, called once at construction.

        A consumer whose rows hold its own store type returns its registry
        subclass here (the seams: ``RegisterRegistry.new_store`` and
        ``new_collector``).
        """
        return RegisterRegistry()

    @property
    def user_items(self) -> Register:
        """The register of the users this worker holds."""
        return self.registry.user_items

    @property
    def connection_items(self) -> Register:
        """The register of the connections this worker holds."""
        return self.registry.connection_items

    @property
    def page_items(self) -> Register:
        """The register of the pages this worker holds."""
        return self.registry.page_items

    @property
    def global_store(self) -> Bag:
        """The replica Bag: local reads, and read-only by convention.

        The single writer is the commander, so a handler that must CHANGE the
        global store either ascends a ``store_set``/``store_del`` or takes
        ``global_store_lock()`` — never writes here.
        """
        return self.global_replica.bag

    @property
    def call_events(self) -> list[dict[str, Any]]:
        """The sink of the CALL being answered in this context.

        Reading it outside a CALL is an impossible case: every lifecycle op is
        reached through ``service_call``, which opens the sink first.
        """
        events = self._call_events.get()
        if events is None:
            raise RuntimeError("lifecycle op outside a CALL")
        return events

    @property
    def call_tasks(self) -> list[dict[str, Any]]:
        """The task sub-envelope of the CALL being answered in this context.

        Read only where ``in_call`` says the sink is open: outside a CALL the
        ascending command has the outbox for a rail, not this list.
        """
        tasks = self._call_tasks.get()
        if tasks is None:
            raise RuntimeError("task sink outside a CALL")
        return tasks

    @property
    def in_call(self) -> bool:
        """Whether this context is serving a CALL — the sinks are open."""
        return self._call_tasks.get() is not None

    @property
    def op_names(self) -> set[str]:
        """The op names this worker routes (its ``@route`` methods)."""
        return set(self.route.nodes(lazy=True).get("entries", {}))

    def attach_channel(self, channel: Any) -> None:
        """Wire an endpoint: its frames come here, its sender wakes on the outbox."""
        self.channel = channel
        channel.on_message = self.handle_frame
        self.outbox.notify = self.notify_sender

    async def start(self) -> None:
        """Start the async sender on the running loop, and the sweep when armed."""
        self._loop = asyncio.get_running_loop()
        self._sender_task = asyncio.create_task(self.sender_loop())
        if self.sweep_interval is not None:
            self._sweep_task = asyncio.create_task(self.sweep_loop())

    async def shutdown(self) -> None:
        """Deliberate stop: cancel the sender and the CALLs in flight, then close.

        The in-flight services die with their REPLYs unsent: the stop is
        deliberate and the channel closes anyway, so nobody is left to read
        them.
        """
        tasks = [
            task
            for task in (self._sender_task, self._sweep_task, *self._service_tasks)
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._sender_task = None
        self._sweep_task = None
        if self.channel is not None:
            await self.channel.close()
        self.pool.shutdown(wait=False)
        self.http_pool.shutdown(wait=False)

    # ------------------------------------------------------------------
    # The wire: a CALL is served on its own task, one REPLY per CALL.
    # ------------------------------------------------------------------

    async def handle_frame(self, frame: Frame) -> None:
        """The channel's ``on_message``: serve a CALL on a task, log anything else.

        Serving is a task, never inline: the receive loop returns to the wire
        immediately, so a slow op cannot make this worker deaf to the next
        CALL. The task ref is held here because the loop keeps only a weak
        one, and dropped when the service ends.

        Inbound EVENTs are the commander's descending pushes, one pipe per
        species — the exchange batch and the dbevents batch — and each is applied
        on a task for the same reason: the work it carries runs on a pool thread
        under the dispatch lock, and the receive loop must not wait for it.

        The global-store pipes are the exception: they are applied INLINE. A
        snapshot must precede the changes that follow it, and this receive loop is
        the only place where that order still exists — a task per frame would let
        a change overtake the seed it applies on top of. Each is cheap by
        ratification (the store is small) and touches no register at all.
        """
        if frame.method == CALL_METHOD:
            self.spawn_service(self.guarded_service(frame))
        elif frame.method == EVENT_METHOD:
            if frame.path == DATACHANGE_IN_PATH:
                self.spawn_service(self.apply_datachange_in(frame.data or []))
            elif frame.path == DBEVENTS_IN_PATH:
                self.spawn_service(self.apply_dbevents_in(frame.data or []))
            elif frame.path == GLOBAL_SNAPSHOT_PATH:
                self.global_replica.load_snapshot(frame.data)
            elif frame.path == GLOBAL_CHANGES_PATH:
                self.global_replica.apply_changes(from_tytx(frame.data, "json"))
            elif frame.path == GLOBAL_GRANT_PATH:
                self.grant_global_lock(frame.data or {})
            else:
                self.logger.debug("%s: no consumer for EVENT %s", self.name, frame.path)
        else:
            self.logger.warning("%s: unexpected envelope %s", self.name, frame.method)

    def spawn_service(self, coro: Any) -> asyncio.Task[None]:
        """Run one inbound frame's work on its own task, holding a strong ref.

        The loop keeps only a weak reference to a task, so the set is what keeps
        the work alive; the shutdown cancels whatever is still in it.
        """
        task = asyncio.create_task(coro)
        self._service_tasks.add(task)
        task.add_done_callback(self._service_tasks.discard)
        return task

    async def guarded_service(self, frame: Frame) -> None:
        """Serve one CALL with the guard INSIDE the task, mirroring the hub's EVENT side.

        An exception that escapes the service — a REPLY the dropped channel
        refused, past ``answer_call``'s own catch — is logged here instead of
        dying unretrieved with the task; a cancellation passes through untouched.
        """
        try:
            await self.service_call(frame)
        except Exception:
            self.logger.exception("%s: service of CALL %s failed", self.name, frame.path)

    async def service_call(self, frame: Frame) -> None:
        """Open this CALL's two sinks, answer it, then close them.

        The sinks are what the REPLY carries besides the browser's own answer:
        the lifecycle this very call produced, and the commands it asks the
        commander to run after the caller is released. Both are held on instance
        ContextVars, so a concurrent CALL — on its own task context — fills its
        own lists and the two never mix.
        """
        token = self._call_events.set([])
        tasks_token = self._call_tasks.set([])
        try:
            await self.answer_call(frame)
        finally:
            self._call_events.reset(token)
            self._call_tasks.reset(tasks_token)

    async def answer_call(self, frame: Frame) -> None:
        """Dispatch one CALL and reply with its result, or with its failure.

        A CALL whose kwargs carry a ``page_id`` is page-addressed: its REPLY is
        also the page's pull cycle, so the drain rides it — see ``send_reply``.
        """
        payload = frame.data or {}
        # The op namespace wins: a CALL whose path names a routed op is that
        # op whatever its kwargs carry — ``http`` is a form, never a reserved
        # word inside the ops' open ``**fields``. Only a path that names no op
        # is probed for the form, at both depths: a hand-built CALL carries it
        # flat, while the front's forward rides the commander's generic
        # envelope, which nests everything the caller passes under ``kwargs``.
        op = frame.path[len(OP_PATH_PREFIX) :] if frame.path.startswith(OP_PATH_PREFIX) else frame.path
        if op not in self.op_names:
            http = payload.get("http") or (payload.get("kwargs") or {}).get("http")
            if http is not None:
                await self.serve_http(frame, http, payload.get("identity"))
                return
        page_id = (payload.get("kwargs") or {}).get("page_id")
        try:
            result = await self.execute(frame.path, payload)
        except Exception as exc:
            self.logger.exception("%s: CALL %s failed", self.name, frame.path)
            await self.send_reply(frame, error=f"{type(exc).__name__}: {exc}", page_id=page_id)
            return
        await self.send_reply(frame, result=result, page_id=page_id)

    async def serve_http(
        self, frame: Frame, http: dict[str, Any], identity: str | None = None
    ) -> None:
        """Serve the http CALL form through the WSGI seam, or refuse it.

        No ``wsgi_app`` means this worker hosts no site: the protocol form is
        understood and the explicit error says the seam is empty. Otherwise the
        environ synthesis and the WSGI call run together on an ``http_pool``
        thread — WSGI is synchronous, and neither the loop nor the op handlers
        may be held behind it. The CALL's ``identity`` travels into the environ.
        """
        if self.wsgi_app is None:
            await self.send_reply(
                frame, error="http CALL form refused: this worker hosts no WSGI site"
            )
            return
        seam = WsgiSeam(self.wsgi_app)
        try:
            reply = await self.http_pool.run(functools.partial(seam.serve, http, identity))
        except Exception as exc:
            self.logger.exception("%s: http CALL %s failed", self.name, frame.path)
            await self.send_reply(frame, error=f"{type(exc).__name__}: {exc}")
            return
        await self.send_reply(frame, result=reply)

    async def execute(self, path: str, payload: dict[str, Any]) -> Any:
        """Resolve the op from the CALL path and run it on its own vehicle."""
        op = path[len(OP_PATH_PREFIX) :] if path.startswith(OP_PATH_PREFIX) else path
        if op not in self.op_names:
            raise LookupError(f"unknown op: {op!r}")
        node = self.route.node(op)
        kwargs = {"identity": payload.get("identity"), **(payload.get("kwargs") or {})}
        if asyncio.iscoroutinefunction(node):
            return await node(**kwargs)
        return await self.pool.run(functools.partial(node, **kwargs))

    async def send_reply(
        self,
        frame: Frame,
        *,
        result: Any = None,
        error: Any = None,
        page_id: str | None = None,
    ) -> None:
        """Answer a CALL, carrying the events and the commands that CALL caused.

        The envelope is causal: the commander folds exactly what this call
        produced, and the delivery is single — the send IS the delivery over UDS
        as over a queue, so there is nothing to ack and nothing to replay.

        Three sub-envelopes travel together: the browser's own answer
        (``result``/``error`` plus ``DELIVERY_KEYS``), the synchronous class the
        commander folds BEFORE releasing it (``events``), and the task class it
        runs after (``tasks`` — the exchange commands this CALL produced for
        targets living elsewhere). An empty class simply carries no key.

        Delivery to the client is PULL, on the page's own request/response
        cycle: when the CALL is page-addressed and that page is still
        registered here, its drain travels under ``DELIVERY_KEYS`` — the two
        species keep their own key, never merged. The outcome of the op does not
        gate it: what is pending for the page is pending either way. A page the
        CALL itself dropped has nothing left to pull, and a CALL that addresses
        no page carries neither key.
        """
        data: dict[str, Any] = {"events": list(self.call_events)}
        if self.call_tasks:
            data["tasks"] = list(self.call_tasks)
        if error is not None:
            data["error"] = error
        else:
            data["result"] = result
        if page_id is not None:
            data.update(await self.pool.run(functools.partial(self.wire_delivery, page_id)))
        await self.channel.send_frame(
            Frame(id=frame.id, method=REPLY_METHOD, path=frame.path, data=data)
        )

    def notify_sender(self) -> None:
        """Outbox wakeup — called on a pool thread as well as on the loop."""
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._outbox_ready.set)

    async def sender_loop(self) -> None:
        """Push the pending lifecycle events as EVENTs whenever the outbox fills."""
        while True:
            await self._outbox_ready.wait()
            self._outbox_ready.clear()
            await self.flush_outbox()

    async def flush_outbox(self) -> None:
        """Drain the pending events onto ``/op/<name>`` EVENTs, then self-ack.

        What comes through here is the out-of-request ascent: the exchange
        whose target lives on another worker, and the lifecycle of a producer
        no CALL is waiting on — the expiry sweep's drops (``offer_lifecycle``).
        The lifecycle a CALL caused rides that CALL's REPLY instead.
        """
        events = self.outbox.drain()
        for event in events:
            await self.channel.send(
                method=EVENT_METHOD, path=f"{OP_PATH_PREFIX}{event['op']}", data=event
            )
        if events:
            self.outbox.drain(events[-1]["seq"])

    @route()
    async def occupancy(self, identity: str | None = None) -> dict[str, Any]:
        """Answer the commander's probe with the current counters.

        Async on purpose: the answer is produced by the loop itself, so a worker
        whose loop is gone cannot produce one — the same exchange carries the
        data and the liveness. ``identity`` is the CALL form's first argument
        and means nothing here: the probe addresses the worker, not a user.
        """
        return self.occupancy_report()

    @route()
    async def monitor_state(self, identity: str | None = None) -> dict[str, Any]:
        """Answer the monitor's fan-out with a scalar projection of the registers.

        One projected row per register entry — identity, ancestry, the activity
        clocks, the edge counts — never the working fields (stores, page
        ``data``, pending ``dbevents``, subscription sets): application content
        is the page's business, not the observer's. Every read is a scalar or
        an atomic copy, so the photo needs no ``dispatch_lock`` and the loop
        takes it itself; a row swept while it is taken is simply not in it —
        the monitor is a poll, the next one shows the world as it settled.
        What only the commander knows — the per-user consumption — is fused up
        there, on arrival. ``identity`` is the CALL form's first argument and
        means nothing here — the fan-out addresses the worker.
        """
        now = time.time()
        return {
            "worker": self.name,
            "users": self.monitor_users(now),
            "connections": self.monitor_connections(now),
            "pages": self.monitor_pages(now),
        }

    def monitor_clocks(self, row: dict[str, Any], now: float) -> dict[str, Any]:
        """The activity clocks of one register row, aged at photo time.

        ``last_refresh_ts`` is the technical contact (every page CALL stamps it
        up the chain) and ``age_s`` its age, computed by the same clock that
        wrote the stamp — floored at 0.0: the photo clock is taken once before
        the walk, and a row stamped WHILE the photo is being taken is simply
        brand new, not from the future. ``last_user_ts`` and ``last_rpc_ts``
        are the daemon's client-reported clocks (siteregister.py:678-690: last
        human input, last real RPC) — None until the page protocol carries the
        ping kwargs that feed them.
        """
        refresh_ts = row["last_refresh_ts"]
        return {
            "last_refresh_ts": refresh_ts,
            "age_s": max(0.0, now - refresh_ts),
            "last_user_ts": row.get("last_user_ts"),
            "last_rpc_ts": row.get("last_rpc_ts"),
        }

    def monitor_users(self, now: float) -> list[dict[str, Any]]:
        """One projected user row: clocks plus connection and page counts.

        The tolerant walk of a lock-free photo: ``keys()`` is a snapshot, and a
        row (or an edge's far end) swept before its read is skipped. ``list``
        on a live set is one atomic copy under the GIL.
        """
        rows: list[dict[str, Any]] = []
        for key in self.user_items.keys():
            row = self.user_items.get(key)
            if row is None:
                continue
            connection_ids = list(row["connections"])
            pages = 0
            for connection_id in connection_ids:
                connection = self.connection_items.get(connection_id)
                if connection is not None:
                    pages += len(connection["pages"])
            rows.append(
                {
                    "register_item_id": key,
                    "connections": len(connection_ids),
                    "pages": pages,
                    **self.monitor_clocks(row, now),
                }
            )
        return rows

    def monitor_connections(self, now: float) -> list[dict[str, Any]]:
        """One projected connection row: owner, clocks, page count."""
        rows: list[dict[str, Any]] = []
        for key in self.connection_items.keys():
            row = self.connection_items.get(key)
            if row is None:
                continue
            rows.append(
                {
                    "register_item_id": key,
                    "user": row["user"],
                    "pages": len(row["pages"]),
                    **self.monitor_clocks(row, now),
                }
            )
        return rows

    def monitor_pages(self, now: float) -> list[dict[str, Any]]:
        """One projected page row: ancestry and clocks, never the working fields."""
        rows: list[dict[str, Any]] = []
        for key in self.page_items.keys():
            row = self.page_items.get(key)
            if row is None:
                continue
            rows.append(
                {
                    "register_item_id": key,
                    "connection_id": row["connection_id"],
                    "root_page_id": row["root_page_id"],
                    "parent_page_id": row["parent_page_id"],
                    "avatar_key": row["avatar_key"],
                    **self.monitor_clocks(row, now),
                }
            )
        return rows

    def occupancy_report(self) -> dict[str, Any]:
        """The worker's raw sensor readings: no percentage, no judgement.

        What the registers can answer, plus the five process gauges the
        commander's evaluator interprets. ``cpu`` is a fraction of the interval
        since the previous report (None on the first one), ``rss`` is bytes
        (None where ``/proc`` is absent), ``reusable`` is the free bytes the C
        heap still holds after the trim (None where ``mallinfo2`` is missing),
        ``trim_s`` is that trim's duration in seconds (None off glibc) — the
        cost reading the policy layer (#5) needs before deciding a commanded,
        conditional trim, ``executor`` is the pressure on the sync-op dispatch
        pool — never the WSGI rail's ``http_pool``.

        The heap is trimmed before the RSS is read: the probe lands here, so
        every reported RSS is measured after the allocator gave back what it
        was only holding.
        """
        trim_s = self.trim_heap()
        metrics = self.pool.metrics
        return {
            "worker": self.name,
            "users": len(self.user_items),
            "pages": len(self.page_items),
            "pending": self.outbox.pending(),
            "seq": self.last_seq,
            "cpu": self.cpu_fraction(),
            "rss": self.rss_bytes(),
            "reusable": self.reusable_bytes(),
            "trim_s": trim_s,
            "executor": {"busy": metrics["busy"], "total": metrics["total"]},
        }

    def cpu_fraction(self) -> float | None:
        """CPU used by this process as a fraction of the wall time since the last call.

        Delta of ``getrusage(RUSAGE_SELF)`` user+system time between two probes,
        over the elapsed monotonic wall clock. None on the first call: there is
        no previous probe to diff against. The probe state lives on this
        instance, never at module level.
        """
        usage = resource.getrusage(resource.RUSAGE_SELF)
        used = usage.ru_utime + usage.ru_stime
        now = time.monotonic()
        previous_ts, previous_used = self.cpu_probe_ts, self.cpu_probe_used
        self.cpu_probe_ts, self.cpu_probe_used = now, used
        if previous_ts is None or previous_used is None or now <= previous_ts:
            return None
        return (used - previous_used) / (now - previous_ts)

    def rss_bytes(self) -> int | None:
        """Resident set size in bytes, read from ``/proc/self/status`` (``VmRSS``).

        None when the file does not exist (no ``/proc``, e.g. macOS) or the
        field is missing. Deliberately /proc-only: no psutil dependency.
        """
        try:
            with open("/proc/self/status", encoding="ascii") as status:
                for line in status:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except OSError:
            return None
        return None

    def resolve_heap_symbols(self) -> tuple[Any | None, Any | None]:
        """The ``malloc_trim``/``mallinfo2`` handles, or None where glibc is absent.

        Called once from ``__init__``: the process C library is not going to
        change underneath a running worker. ``restype``/``argtypes`` are set
        here, so the callers just call. Both handles are independent — a libc
        with one symbol and not the other loses only that gauge. A C runtime
        with no global handle at all (Windows raises TypeError, a restricted
        loader OSError) loses both — the same degradation contract as
        ``rss_bytes`` where ``/proc`` is absent.
        """
        try:
            libc = ctypes.CDLL(None)
        except (OSError, TypeError):
            return None, None
        trim = getattr(libc, "malloc_trim", None)
        if trim is not None:
            trim.argtypes = [ctypes.c_size_t]
            trim.restype = ctypes.c_int
        info = getattr(libc, "mallinfo2", None)
        if info is not None:
            info.argtypes = []
            info.restype = MallInfo2
        return trim, info

    def trim_heap(self) -> float | None:
        """Return the C heap's free pages to the OS (``malloc_trim(0)``).

        Linux/glibc only: a silent no-op answering None where the symbol is
        missing, same contract as ``rss_bytes()``. An in-process call — no
        restart, no object touched — whose point is that the RSS read right
        after is not measuring memory the allocator already considers free.
        Returns the walk's duration in seconds: the trim runs on the loop and
        takes the arena locks, so its cost is a reading the policy layer
        (issue #5) needs before deciding a commanded, conditional trim.
        ``malloc_trim``'s own return (whether anything was released) carries
        no decision and is discarded.
        """
        if self.libc_malloc_trim is None:
            return None
        start = time.monotonic()
        self.libc_malloc_trim(0)
        return time.monotonic() - start

    def reusable_bytes(self) -> int | None:
        """Free bytes held by the C heap (``mallinfo2().fordblks``).

        The honest half of the memory reading: the free bytes the C heap still
        holds after the trim, which the allocator can hand out again without
        growing. An ESTIMATE, bounded on both sides: ``mallinfo2`` reports the
        MAIN arena only while the trim frees every arena, so free bytes parked
        in a threaded worker's secondary arenas count in ``rss`` and not here
        (``rss - reusable`` then OVER-reads live memory — the busier the
        worker, the more arenas); conversely the trim madvises chunks away
        while they keep counting in ``fordblks`` (an under-read, floored by
        the evaluator's clamp). None where ``mallinfo2`` is missing (macOS,
        musl, glibc < 2.33) — the evaluator then reads plain RSS, exactly as
        before this gauge existed.
        """
        if self.libc_mallinfo2 is None:
            return None
        return int(self.libc_mallinfo2().fordblks)

    # ------------------------------------------------------------------
    # The live stores: one drain point, one forwarded-write primitive.
    # ------------------------------------------------------------------

    def wire_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        """The wire-safe view of a register row: the live objects stay here.

        An op result travels as JSON, and a Bag or a collector is not a value
        the wire can carry — nor should it: a store is worker memory, and the
        one legitimate way for it to leave is the move package. The subscription
        sets of a page row are values, so they travel — as sorted lists, JSON
        having no set.
        """
        return {
            key: sorted(value) if isinstance(value, set) else value
            for key, value in entry.items()
            if key not in LIVE_ROW_FIELDS
        }

    def collect_page(self, page_id: str) -> dict[str, Any]:
        """Drain everything pending for one page, in the three-species shape.

        The single drain point: the page's own filtered collector and its
        ``user_view`` (when it has one) are drained together and merged by
        ``change_ts`` — the sort is stable, so two changes stamped alike keep
        the order they were collected in. The dbevents are their own species
        and travel in their own key, never dressed as datachanges.

        The whole drain runs under ``dispatch_lock``, the same lock the pool
        threads hold when they deposit: without it the read-and-reset window
        can lose a deposit landing between the drain and the swap. The lock is
        an RLock, so ``evict_pages`` — which already holds it — re-enters
        safely.

        Raises ``KeyError`` if ``page_id`` is not registered here.
        """
        with self.dispatch_lock:
            page = self.page_items.get(page_id)
            if page is None:
                raise KeyError(f"collect_page: unknown page {page_id!r}")
            datachanges = page["collector"].drain()
            if page["user_view"] is not None:
                datachanges.extend(page["user_view"].drain())
            dbevents = page["dbevents"]
            page["dbevents"] = []
        datachanges.sort(key=lambda change: change["change_ts"])
        return {"datachanges": datachanges, "dbevents": dbevents}

    def refresh_chain(self, page_id: str) -> float:
        """Stamp the page and the chain above it with the server's own clock.

        The daemon's ``refresh`` (siteregister.py:678-690) climbs exactly this
        way — page, its connection, its user — and stamps them with an instant
        it takes itself: a client value never touches these rows, so a page
        cannot buy immortality by lying about its own activity. Returns the
        instant written, which is what makes the stamping assertable.
        """
        now = time.time()
        with self.dispatch_lock:
            page = self.page_items.get(page_id)
            page["last_refresh_ts"] = now
            connection = self.connection_items.get(page["connection_id"])
            connection["last_refresh_ts"] = now
            self.user_items.get(connection["user"])["last_refresh_ts"] = now
        return now

    def wire_delivery(self, page_id: str) -> dict[str, Any]:
        """The server side of one pull cycle: the refresh stamp, then the drain.

        A change is not a JSON value: it carries the node's own value (a Bag when
        the write created an intermediate node) and a ``change_ts`` datetime. So
        each species travels TYTX-encoded, the same vehicle the move package uses
        for a store — the reader hydrates it with ``from_tytx``. The frame codec
        stays untouched.

        The refresh rides here because a page-addressed CALL IS the page's sign
        of life, and this is the trip that CALL already makes: both halves run
        under one hold of ``dispatch_lock`` (an RLock, so each takes it again on
        its own account). It drains, so it runs off the loop, through the pool —
        the op INVARIANT holds here too.

        The existence check lives INSIDE the lock hold, because the trip is a
        thread handoff: a page the CALL itself dropped, or one a concurrent
        eviction took between the CALL and its REPLY, is found gone HERE and
        yields an empty delivery — the REPLY still departs. A check on the loop
        side would be a decision taken before the window it decides about.
        """
        with self.dispatch_lock:
            if self.page_items.get(page_id) is None:
                return {}
            self.refresh_chain(page_id)
            collected = self.collect_page(page_id)
        return {key: to_tytx(collected[key], "json") for key in DELIVERY_KEYS}

    def apply_forwarded(self, bag: Bag, change: dict[str, Any]) -> None:
        """Apply a change born elsewhere to a local Bag (STATE delivery).

        The write is a real write, so the local collectors capture it with a
        local ``change_ts``: ordering stays on local time. What the producer
        knew travels as ``_original_ts``, an attribute added to the ones the
        change carried — ratified convention, and a declared residue on the
        node. A delete removes the node: setting None would be a different
        state from *gone*.
        """
        path = change["key"]["path"]
        reason = change["key"]["reason"]
        if change["delete"]:
            bag.pop(path, _reason=reason)
            return
        attributes = dict(change["attributes"] or {})
        attributes["_original_ts"] = change["change_ts"]
        bag.set_item(
            path,
            change["value"],
            _attributes=attributes,
            _reason=reason,
            _fired=change["key"]["fired"],
        )

    # ------------------------------------------------------------------
    # The addressed write: three tiers, one switch. A message is the thin
    # readable header (op, kind, target, filters) plus the TYTX parcel the
    # commander never opens.
    # ------------------------------------------------------------------

    def exchange_message(
        self,
        op: str,
        *,
        kind: str,
        target: str | None,
        filters: str | None,
        **payload: Any,
    ) -> dict[str, Any]:
        """The message one exchange op travels as, ascending or descending.

        Flat and readable on purpose: the commander routes on ``kind``,
        ``target`` and ``filters`` alone. ``payload`` is what the op adds — the
        TYTX-encoded ``change`` of a ``set_datachange``, the ``path`` of a
        ``drop_datachanges``.
        """
        if filters is not None and kind != SIGNAL_KIND:
            raise ValueError(f"{op}: a filtered address names pages, not {kind!r}")
        return {"op": op, "kind": kind, "target": target, "filters": filters, **payload}

    def route_datachange(self, message: dict[str, Any]) -> None:
        """The switch: apply here, or send it up. Called with ``dispatch_lock`` held.

        Tier 2 is the whole point of usersticky — a target this worker holds
        costs no channel traffic at all. Tier 3 is everything else: the message
        ascends for the commander, which alone sees every page, to resolve. A
        filtered broadcast always ascends for that same reason.

        Which rail it ascends on depends on WHO produced it. Inside a CALL the
        command joins that CALL's task sub-envelope and travels on its REPLY:
        one exchange instead of two, with full causal attribution. Outside any
        CALL — a background task, a handler of its own — the outbox with its
        per-seq ack is the rail, as before.
        """
        if message["filters"] is None and self.holds_target(message):
            self.apply_datachange(message)
            return
        command = self.shape_exchange(message)
        if self.in_call:
            self.call_tasks.append(command)
            return
        self.outbox.offer(command)

    def target_row(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """The register row a message addresses, or None when it is not here.

        ``kind`` chooses the register: ``user_store`` names a user,
        ``connection_store`` names a session id, every other kind names a page.
        """
        kind = message["kind"]
        if kind == "user_store":
            register = self.user_items
        elif kind == "connection_store":
            register = self.connection_items
        else:
            register = self.page_items
        return register.get(message["target"])

    def holds_target(self, message: dict[str, Any]) -> bool:
        """Whether the message's target is registered on this worker."""
        return self.target_row(message) is not None

    def apply_datachange(self, message: dict[str, Any]) -> None:
        """Apply one message to a target of this worker. Under ``dispatch_lock``.

        The state/signal split lands here: a store address is a real Bag write,
        a page address is a deposit on that page's collector. The parcel is
        decoded at this single point — it travelled TYTX from wherever it was
        produced, ``replace`` riding beside it: the deposit coalesces with the
        pending change of the same key when the producer asked for it.
        """
        row = self.target_row(message)
        op = message["op"]
        if op == "reset_datachanges":
            row["collector"].reset()
        elif op == "drop_datachanges":
            row["collector"].drop(message["path"])
        elif message["kind"] in STATE_KINDS:
            self.apply_forwarded(row["store"], from_tytx(message["change"], "json"))
        else:
            row["collector"].append(
                from_tytx(message["change"], "json"), replace=message["replace"]
            )

    async def apply_datachange_in(self, batch: list[dict[str, Any]]) -> None:
        """Apply one descending batch — the arrival of the internal rail.

        Off the loop: every message in it takes ``dispatch_lock`` and may write
        a Bag. A target that vanished while the batch was on the wire is dropped
        with a debug log — a change is a signal and there is no retry queue.
        """
        try:
            await self.pool.run(functools.partial(self.apply_datachange_batch, batch))
        except Exception:
            self.logger.exception("%s: datachange_in batch failed", self.name)

    def apply_datachange_batch(self, batch: list[dict[str, Any]]) -> None:
        """Apply a whole descending batch under one lock, skipping the dead targets."""
        with self.dispatch_lock:
            for message in batch:
                if self.holds_target(message):
                    self.apply_datachange(message)
                else:
                    self.logger.debug(
                        "%s: datachange_in dropped, no target %r",
                        self.name,
                        message.get("target"),
                    )

    @route()
    def set_datachange(
        self,
        identity: str,
        change: str,
        kind: str = SIGNAL_KIND,
        target: str | None = None,
        filters: str | None = None,
        replace: bool = False,
        **addressing: Any,
    ) -> dict[str, Any]:
        """Write a change toward a target that may live anywhere.

        ``change`` is the TYTX-encoded change dict, ``kind`` says what ``target``
        names (a page store, a user store, or the page itself), and ``filters``
        is the alternative address: the broadcast the commander resolves over
        every page it knows. ``addressing`` absorbs the caller's own ``page_id``
        — the pull cycle of the CALL, never the target of the write.

        ``replace=True`` coalesces: on a SIGNAL address the deposit drops the
        pending change of the same key — same path, same reason, same fired —
        so a value written over and over reaches the browser once. It is the
        daemon's own dedup, which compares ClientDataChange on those very three
        fields.
        """
        with self.dispatch_lock:
            message = self.exchange_message(
                "set_datachange",
                kind=kind,
                target=target,
                filters=filters,
                change=change,
                replace=replace,
            )
            self.route_datachange(message)
        return {"kind": kind, "target": target, "filters": filters, "replace": replace}

    @route()
    def reset_datachanges(
        self,
        identity: str,
        target: str | None = None,
        filters: str | None = None,
        **addressing: Any,
    ) -> dict[str, Any]:
        """Empty the pending changes of the addressed page(s) without reading them."""
        with self.dispatch_lock:
            message = self.exchange_message(
                "reset_datachanges", kind=SIGNAL_KIND, target=target, filters=filters
            )
            self.route_datachange(message)
        return {"target": target, "filters": filters}

    @route()
    def drop_datachanges(
        self,
        identity: str,
        path: str,
        target: str | None = None,
        filters: str | None = None,
        **addressing: Any,
    ) -> dict[str, Any]:
        """Discard the pending changes under ``path`` on the addressed page(s)."""
        with self.dispatch_lock:
            message = self.exchange_message(
                "drop_datachanges",
                kind=SIGNAL_KIND,
                target=target,
                filters=filters,
                path=path,
            )
            self.route_datachange(message)
        return {"target": target, "filters": filters, "path": path}

    @route()
    def setStoreSubscription(  # noqa: N802 - reserved protocol name, transcribed verbatim
        self,
        identity: str,
        page_id: str,
        storename: str,
        prefix: str,
        active: bool = True,
    ) -> dict[str, Any]:
        """Open (or close) a page's window onto a store, by path prefix.

        The daemon generates a datachange only for a path the page subscribed,
        and this is the op that declares those prefixes. ``storename='page'``
        acts on the page's OWN collector — the row's ``subscribed_paths`` and
        the collector's prefix set move together, the set being what a move
        packages and the collector what the drain reads. ``storename='user'``
        acts on ``user_view``, the collector on the owner's Bag: opening one
        creates or widens it, closing one narrows it, and a page that never
        opened any has nothing to close.

        Entirely LOCAL: the page lives on this worker by stickiness and both
        collectors are objects of this process, so nothing ascends. Any other
        storename is an impossible address and raises ``ValueError``.
        """
        with self.dispatch_lock:
            page = self.page_items.get(page_id)
            if page is None:
                raise KeyError(f"setStoreSubscription: unknown page {page_id!r}")
            if storename == "page":
                if active:
                    page["subscribed_paths"].add(prefix)
                    page["collector"].subscribe_path(prefix)
                else:
                    page["subscribed_paths"].discard(prefix)
                    page["collector"].unsubscribe_path(prefix)
            elif storename == "user":
                if active:
                    self.registry.subscribe_store_path(page_id, prefix)
                else:
                    page["store_subscriptions"].discard(prefix)
                    if page["user_view"] is not None:
                        page["user_view"].unsubscribe_path(prefix)
            else:
                raise ValueError(f"setStoreSubscription: unknown storename {storename!r}")
        return {"page_id": page_id, "storename": storename, "prefix": prefix, "active": active}

    # ------------------------------------------------------------------
    # dbevents: their own ops, their own index, their own pipe. Nothing here
    # ever touches a collector — a deposit is not a change.
    # ------------------------------------------------------------------

    @route()
    def subscribeTable(  # noqa: N802 - reserved protocol name, transcribed verbatim
        self,
        identity: str,
        table: str,
        page_id: str,
        subscribe: bool = True,
        subscribeMode: str | None = None,  # noqa: N803 - reserved protocol name
    ) -> dict[str, Any]:
        """Subscribe (or unsubscribe) the CALLING page to a table's events.

        ``page_id`` is the caller's own page here — the subscriber is whoever
        asks — so the same field that names the pull cycle of this CALL names
        the subscription's owner, and there is no target to address.

        ``subscribeMode`` is vestigial: the daemon accepts it and reads it
        nowhere, and callers still pass it, so refusing it would break them at
        mount time. It is accepted and ignored, exactly as the daemon does.

        The row's ``table_subscriptions`` set and the index move together: the
        set is what a move packages, the index is what the fan-out reads. Then
        the subscription ascends, because the commander is the only surface that
        can reach the subscribers sitting on the OTHER workers.
        """
        with self.dispatch_lock:
            page = self.page_items.get(page_id)
            if page is None:
                raise KeyError(f"subscribeTable: unknown page {page_id!r}")
            if subscribe:
                page["table_subscriptions"].add(table)
                self.subscriptions.subscribe(page_id, table)
            else:
                page["table_subscriptions"].discard(table)
                self.subscriptions.unsubscribe(page_id, table)
            self.outbox.offer(
                self.shape_ascending(
                    "subscribeTable", page_id=page_id, table=table, subscribe=subscribe
                )
            )
        return {"page_id": page_id, "table": table, "subscribe": subscribe}

    @route()
    def notifyDbEvents(  # noqa: N802 - reserved protocol name, transcribed verbatim
        self,
        identity: str,
        dbevents: dict[str, Any],
        reason: str | None = None,
        page_id: str | None = None,
        local_only: bool = False,
        **addressing: Any,
    ) -> dict[str, Any]:
        """Announce a commit's table events: locally at once, then everywhere else.

        ``dbevents`` is ``{table: batch}``; ``page_id`` is the origin page (the
        caller's own, as everywhere), and it travels as ``from_page_id`` so a
        subscriber can tell its own commit from somebody else's.

        The deposits are shaped once, here: the local subscribers get them
        immediately — zero channel traffic for a co-located page — and the very
        same objects ascend, so a remote subscriber reads the origin's ``ts``.
        The commander excludes this worker from its own fan-out, so nothing is
        served twice; a table nobody subscribed anywhere costs no send at all.

        ``local_only`` is the hidden transaction: the events belong to the page
        that made them and to nobody else, so the deposits land on the origin
        page alone — no fan-out to the other local subscribers, no ascent, and
        no table-cache invalidation. The legacy routes that case to the page's
        own notify and never runs the cache check on it.
        """
        deposits = [
            self.dbevent_deposit(table, batch, page_id, reason)
            for table, batch in (dbevents or {}).items()
            if batch
        ]
        if local_only:
            with self.dispatch_lock:
                for deposit in deposits:
                    self.deposit_dbevent(page_id, deposit)
            return {"tables": [deposit["table"] for deposit in deposits]}
        with self.dispatch_lock:
            for deposit in deposits:
                self.invalidate_table_cache(deposit["table"])
                self.fan_out_local(deposit)
            if deposits:
                self.outbox.offer(self.shape_ascending("notifyDbEvents", deposits=deposits))
        return {"tables": [deposit["table"] for deposit in deposits]}

    def dbevent_deposit(
        self,
        table: str,
        batch: Any,
        from_page_id: str | None,
        reason: str | None,
    ) -> dict[str, Any]:
        """The deposit one table's batch becomes in a page's ``dbevents`` list.

        JSON by construction — ``ts`` is an epoch float, the batch is what the
        caller handed over — so it rides the internal rail as it is and reaches
        the client through the same ``to_tytx`` the delivery encodes everything
        with.
        """
        return {
            "table": table,
            "batch": batch,
            "from_page_id": from_page_id,
            "reason": reason,
            "ts": time.time(),
        }

    def fan_out_local(self, deposit: dict[str, Any]) -> None:
        """Deposit one shaped deposit on THIS worker's subscribing pages. Under lock.

        The index answers with a copy of the subscriber set, so a subscription
        arriving mid-fan-out cannot disturb it. Zero subscribers is one dict
        lookup that misses.
        """
        for page_id in self.subscriptions.pages_for(deposit["table"]):
            self.deposit_dbevent(page_id, deposit)

    def deposit_dbevent(self, page_id: str | None, deposit: dict[str, Any]) -> None:
        """Append one deposit to a page's own pending list. Under ``dispatch_lock``.

        A page this worker does not hold — dropped, or moved while the batch was
        on the wire — loses the deposit with a debug log: a dbevent is a signal.
        """
        page = self.page_items.get(page_id)
        if page is None:
            self.logger.debug("%s: dbevent dropped, no page %r", self.name, page_id)
            return
        page["dbevents"].append(deposit)

    # ------------------------------------------------------------------
    # The table cache: an observer per page store records what a table cached
    # there, a dbevent on that table writes None over it.
    # ------------------------------------------------------------------

    def cache_observer_id(self, page_id: str) -> str:
        """The Bag subscriber id of a page's cache observer.

        The observer IS the worker, so its own ``id()`` would not tell two
        pages apart: the page id is what discriminates, one observer per page
        store.
        """
        return f"cached_tables_{page_id}"

    def attach_cache_observer(self, page_id: str, store: Bag) -> None:
        """Watch a page's own store for the writes that declare a cached table.

        A dedicated subscription, never the page collector: the recording must
        happen for EVERY caching write, whatever prefixes the page subscribed
        (daemon ``_on_data_trigger``, siteregister.py:150-156, records before
        and outside its prefix match). Updates and inserts only — a delete
        takes the cached value away with the node, so there is nothing left to
        invalidate.
        """
        store.subscribe(
            self.cache_observer_id(page_id),
            update=functools.partial(self.on_cache_update, page_id),
            insert=functools.partial(self.on_cache_insert, page_id),
        )

    def on_cache_update(self, page_id: str, **kwargs: Any) -> None:
        """Record an updated node that names a cached table. Never returns False."""
        node = kwargs["node"]
        self.record_cached_path(page_id, ".".join(kwargs["pathlist"] or []), node)

    def on_cache_insert(self, page_id: str, **kwargs: Any) -> None:
        """Record an inserted node that names a cached table.

        The insert event reports the path of the PARENT, so the node's own
        label completes it — the same rebuild the collector does.
        """
        node = kwargs["node"]
        path = ".".join(list(kwargs["pathlist"] or []) + [node.label])
        self.record_cached_path(page_id, path, node)

    def record_cached_path(self, page_id: str, path: str, node: Any) -> None:
        """Index one caching write; a node with no ``_caching_table`` is ignored.

        This runs inside Bag trigger dispatch, on whatever thread wrote the
        store, so it takes ``dispatch_lock`` — reentrant, so a write already
        made under the lock stays safe.
        """
        table = node.attr.get("_caching_table")
        if not table:
            return
        with self.dispatch_lock:
            self.cached_tables.setdefault(table, {}).setdefault(page_id, set()).add(path)

    def drop_page_cache(self, page_id: str) -> None:
        """Stop watching a page's store and forget its cached paths.

        The mirror of ``subscriptions.drop_page``: the page leaves every table
        entry and an emptied table leaves no entry behind. Called while the row
        is still there — the store is reached through it.
        """
        with self.dispatch_lock:
            store = self.page_items.get(page_id)["store"]
            store.unsubscribe(self.cache_observer_id(page_id), update=True, insert=True)
            for table in list(self.cached_tables):
                pages = self.cached_tables[table]
                pages.pop(page_id, None)
                if not pages:
                    del self.cached_tables[table]

    def invalidate_table_cache(self, table: str) -> None:
        """Write None over every path a table cached, page by page. Under lock.

        Transcribed from ``invalidateTableCache`` (siteregister.py:163-170):
        the table's entry is popped and each cached path is set to None with a
        real store write, so the page's own filtered collector captures the
        invalidation when — and only when — that page subscribed the path. The
        node keeps its ``_caching_table`` attribute, so the observer records
        the path again: the daemon re-fills its index the same way, and the
        entry simply describes a cache holding None until the next real read.
        A table nobody cached costs one dict lookup that misses.
        """
        with self.dispatch_lock:
            table_cache = self.cached_tables.pop(table, None)
            if table_cache is None:
                return
            for page_id, paths in table_cache.items():
                page = self.page_items.get(page_id)
                if page is None:
                    self.logger.debug("%s: cache invalidation, no page %r", self.name, page_id)
                    continue
                for path in paths:
                    page["store"][path] = None

    async def apply_dbevents_in(self, batch: list[dict[str, Any]]) -> None:
        """Apply one descending dbevents batch — the arrival of its own pipe.

        Off the loop, like the exchange side: every item takes ``dispatch_lock``.
        """
        try:
            await self.pool.run(functools.partial(self.apply_dbevents_batch, batch))
        except Exception:
            self.logger.exception("%s: dbevents_in batch failed", self.name)

    def apply_dbevents_batch(self, batch: list[dict[str, Any]]) -> None:
        """Deposit a whole descending batch under one lock, page by page.

        The tables are invalidated FIRST — the daemon's order, cache check
        before the fan-out (siteregister.py:490-496) — and once each: a batch
        names the same table for every subscribing page, and the invalidation is
        worker-wide.
        """
        with self.dispatch_lock:
            for table in dict.fromkeys(item["deposit"]["table"] for item in batch):
                self.invalidate_table_cache(table)
            for item in batch:
                self.deposit_dbevent(item["page_id"], item["deposit"])

    # ------------------------------------------------------------------
    # The global store: read from the replica, written above. Nothing here
    # writes ``global_store`` — a change reaches it only as a descending push.
    # ------------------------------------------------------------------

    def run_on_loop(self, coro: Any) -> Any:
        """Run a coroutine on this worker's loop from a pool thread, and wait.

        The bridge the sync form of ``global_store_lock`` needs: a sync op
        handler is on a pool thread, where blocking costs nothing, but the grant
        it waits for arrives on the loop.
        """
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    @route()
    def store_set(self, identity: str, path: str, value: Any = None, **addressing: Any) -> Any:
        """Write one path of the global store — the master is above, so it ascends.

        Nothing is written locally: the change comes back down the ordinary
        ``GLOBAL_CHANGES_PATH`` batch, so this worker's replica is updated by the
        same push that updates everybody else's. One writer, one order.
        """
        self.offer_ascending("store_set", path=path, value=value)
        return {"path": path}

    @route()
    def store_del(self, identity: str, path: str, **addressing: Any) -> Any:
        """Remove one path of the global store — it ascends exactly like a write."""
        self.offer_ascending("store_del", path=path)
        return {"path": path}

    def global_store_lock(self) -> GlobalStoreLease:
        """One hold of the global store: ``with`` on a pool thread, ``async with`` on the loop."""
        return GlobalStoreLease(self)

    async def acquire_global_lock(self, request_id: str) -> CapturingGlobalStore:
        """Ask for the master and mount what comes back as a working copy.

        The grant carries the store itself, so there is no staleness question to
        answer: the copy IS the master at grant time. It is hydrated BEFORE its
        collector attaches — a captured hydration would ship the whole store back
        at release.

        The ascending request is queued through the pool: ``dispatch_lock`` is
        taken there, never on this coroutine's loop thread.
        """
        granted: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self.global_grants[request_id] = granted
        await self.pool.run(
            functools.partial(self.offer_ascending, "store_lock", request_id=request_id)
        )
        try:
            store = await granted
        finally:
            del self.global_grants[request_id]
        return CapturingGlobalStore(from_tytx(store, "json"))

    async def release_global_lock(
        self, request_id: str, copy: CapturingGlobalStore, apply: bool = True
    ) -> None:
        """Hand the drained changes back to the master and let the copy go.

        The changes land on the master only here, so the whole lock is
        all-or-nothing: a body that raised releases with nothing to apply,
        exactly as a holder's death does. The copy is detached either way — the
        author's replica is updated by the propagation like everybody else's.
        The ascent is queued through the pool, like the acquire's.
        """
        changes = copy.drain() if apply else []
        copy.detach()
        await self.pool.run(
            functools.partial(
                self.offer_ascending,
                "store_unlock",
                request_id=request_id,
                changes=to_tytx(changes, "json"),
            )
        )

    def grant_global_lock(self, grant: dict[str, Any]) -> None:
        """Hand a descending grant to the coroutine parked on it.

        A grant nobody waits for is dropped with a debug log: the acquire was
        cancelled, and there is no lock to hold on its behalf — the commander
        releases it when this channel ends.
        """
        future = self.global_grants.get(grant["request_id"])
        if future is None or future.done():
            self.logger.debug(
                "%s: global grant %s has no parked caller", self.name, grant["request_id"]
            )
            return
        future.set_result(grant["store"])

    # ------------------------------------------------------------------
    # Event shaping: the seq is minted here, under the dispatch lock, so the
    # commander folds in the order this worker mutated.
    # ------------------------------------------------------------------

    def shape_event(self, op: str, **payload: Any) -> dict[str, Any] | None:
        """Shape a lifecycle op into the flat event the commander folds.

        An operational op returns ``None``: it stays worker-local. The event
        carries scalars only — op, seq, the worker name and the entity keys.
        Called with ``dispatch_lock`` held (the seq bump is serialized).
        """
        if op not in LIFECYCLE_OPS:
            return None
        self.last_seq += 1
        return {"op": op, "seq": self.last_seq, "worker": self.name, **payload}

    def shape_ascending(self, op: str, **payload: Any) -> dict[str, Any]:
        """Stamp an ascending message with its seq and its origin worker.

        One shaper for the POST and global-store rails: the ``worker`` stamp
        is what the commander excludes from a dbevents fan-out — a message
        that lost it would be served twice — and the name it grants a global
        lock to and releases when that channel ends. Called with
        ``dispatch_lock`` held, like every seq bump.
        """
        self.last_seq += 1
        return {"op": op, "seq": self.last_seq, "worker": self.name, **payload}

    def offer_ascending(self, op: str, **payload: Any) -> None:
        """Take ``dispatch_lock``, shape one ascending message and queue it.

        The sync half of the ascent: sync op handlers call it on their own
        pool thread, and the loop-side callers (the global-lock pair) hand it
        to the pool — the loop never waits on ``dispatch_lock``, because a
        long hold elsewhere (a move packaging, a whole descending batch)
        would freeze every coroutine with it (see the op INVARIANT below).
        """
        with self.dispatch_lock:
            self.outbox.offer(self.shape_ascending(op, **payload))

    def shape_exchange(self, message: dict[str, Any]) -> dict[str, Any]:
        """Stamp an ascending exchange message with its seq and its origin.

        The outbox is the async rail (design D4, idle until now): its drain
        sends one EVENT per message on ``/op/<op>``, and the seq is what the
        drain acks. Called with ``dispatch_lock`` held, like every seq bump.
        """
        self.last_seq += 1
        return {"seq": self.last_seq, "worker": self.name, **message}

    def offer_event(self, op: str, **payload: Any) -> dict[str, Any] | None:
        """Shape a lifecycle op and append it to the sink of the CALL causing it."""
        event = self.shape_event(op, **payload)
        if event is not None:
            self.call_events.append(event)
        return event

    def offer_lifecycle(self, op: str, **payload: Any) -> dict[str, Any] | None:
        """Shape a lifecycle op and queue it on the outbox — the CALL-less rail.

        The sibling of ``offer_event`` for a producer nobody is waiting on: the
        expiry sweep runs on its own clock, outside any CALL, so its drops have
        no REPLY envelope to ride and take the outbox with its per-seq ack.
        """
        event = self.shape_event(op, **payload)
        if event is not None:
            self.outbox.offer(event)
        return event

    # ------------------------------------------------------------------
    # User lifecycle ops — the active subset of the vocabulary. Each mutates
    # the register and offers its event under one lock.
    # INVARIANT: an op that takes ``dispatch_lock`` is sync — it runs on a
    # pool thread, where blocking costs nothing. An async op must never take
    # it: served on the loop's own task, it would block the whole event loop
    # while a pool thread holds the lock.
    # ------------------------------------------------------------------

    @route()
    def new_user(self, identity: str, **fields: Any) -> dict[str, Any]:
        """Create the user entry of ``identity`` and announce it."""
        with self.dispatch_lock:
            entry = self.registry.new_user(identity, **fields)
            self.offer_event("new_user", user=identity)
            return self.wire_entry(entry)

    @route()
    def new_connection(self, identity: str, **fields: Any) -> dict[str, Any]:
        """Create the connection row of ``identity`` and announce it.

        The reception: a connection arrives anonymous, so
        ``Registry.new_connection`` names it ``GUEST_PREFIX`` + the session id
        and brings that guest user entry into being with it — the surface hears
        the cascade in the order it happened, the ``new_user`` it really is and
        then the connection.
        """
        with self.dispatch_lock:
            user_name = fields.get("user") or GUEST_PREFIX + identity
            unseen_user = user_name not in self.user_items
            entry = self.registry.new_connection(identity, **fields)
            if unseen_user:
                self.offer_event("new_user", user=entry["user"])
            self.offer_event("new_connection", user=entry["user"], session_id=identity)
            return self.wire_entry(entry)

    @route()
    def change_connection_user(self, identity: str, user: str, **fields: Any) -> dict[str, Any]:
        """Re-label the connection ``identity`` onto the logged-in ``user``, in place.

        The login transition: the sticky key of the CONNECTION stops being the
        anonymous one (its own session id) and becomes the root avatar identity.
        Nothing dies at login — ``Registry.change_connection_user`` mutates
        the live connection row; on a first login the anonymous user entry is
        transferred whole onto the new key (store included, the registry's
        declared divergence), otherwise the old user leaves only once its
        ``connections`` set is empty. When this worker already hosts the target
        user the registry's join is the whole login: the connection is linked
        to the resident entry and its pages' ``user_view`` is re-attached to
        the resident store.

        **The login never ships** (ratified 2026-08-12): whatever the commander
        later decides, the slice stays HERE — the request that carried the
        login keeps finding its pages on this worker to the end. The event
        announces the re-label on the REPLY; the commander maps the user where
        it was born and, when it belongs elsewhere, orders the ordinary
        commanded move (``evict_user`` → ``add_user``) as a task of its own.
        The returned entry is the snapshot the caller logged in with.
        """
        with self.dispatch_lock:
            connection = self.connection_items.get(identity)
            if connection is None:
                raise KeyError(f"change_connection_user: unknown connection {identity!r}")
            previous_user = connection["user"]
            self.registry.change_connection_user(identity, user, **fields)
            entry = self.user_items.get(user)
            self.offer_event(
                "change_connection_user",
                user=user,
                previous_user=previous_user,
                session_id=identity,
            )
            return self.wire_entry(entry)

    @route()
    def drop_user(self, identity: str) -> dict[str, Any]:
        """Drop the user entry (and its pages) and announce it.

        The pages to forget in the subscription index and in the table cache are
        collected by walking the tree down — the user entry's ``connections``,
        each connection's ``pages`` — before the registry demolishes it.
        """
        with self.dispatch_lock:
            entry = self.user_items.get(identity)
            if entry is None:
                raise KeyError(f"drop_user: unknown user {identity!r}")
            for connection_id in entry["connections"]:
                for page_id in self.connection_items.get(connection_id)["pages"]:
                    self.subscriptions.drop_page(page_id)
                    self.drop_page_cache(page_id)
            entry = self.registry.drop_user(identity)
            self.offer_event("drop_user", user=identity)
            return self.wire_entry(entry)

    # ------------------------------------------------------------------
    # Page lifecycle ops — the emitters the commander's page surface folds.
    # Same discipline as the user ops: one lock, one event, a wire view back.
    # ------------------------------------------------------------------

    @route()
    def new_page(self, identity: str, page_id: str, **fields: Any) -> dict[str, Any]:
        """Create the page row of ``page_id`` under ``identity`` and announce it.

        ``Registry.new_page`` brings the whole chain into being from the bottom
        up — the user entry and the connection row with the first page of them —
        so the surface hears that cascade first, in the order it happened: the
        ``new_user`` it really is, then the ``new_connection``, then the page.
        The page event names its connection (``session_id``): the surface's page
        row is the bottom of that same chain and the login mutates it there.
        """
        with self.dispatch_lock:
            connection_id = fields.get("connection_id") or fields.get("session_id")
            unseen_user = identity not in self.user_items
            unseen_connection = connection_id not in self.connection_items
            entry = self.registry.new_page(page_id, user=identity, **fields)
            self.attach_cache_observer(page_id, entry["store"])
            if unseen_user:
                self.offer_event("new_user", user=identity)
            if unseen_connection:
                self.offer_event("new_connection", user=identity, session_id=entry["connection_id"])
            self.offer_event(
                "new_page", user=identity, page_id=page_id, session_id=entry["connection_id"]
            )
            return self.wire_entry(entry)

    def demolish_page(self, page_id: str, announce: Callable[..., Any]) -> dict[str, Any]:
        """Take one page off this worker and announce the cascade its drop causes.

        ``Registry.drop_page`` takes the connection away with the last page of
        it, and the user with the last connection of that user, so the surface
        must hear about those too: the cascade is announced, in the order it
        climbs, as the ``drop_connection`` and ``drop_user`` it really is, right
        after the page event.

        The owner is resolved BEFORE the drop: it is derived through the chain,
        and the chain is exactly what the cascade may tear down. The cache
        observer goes the same way, while the row is still there to reach the
        store through.

        ``announce`` is the rail the caller has: an op inside a CALL passes
        ``offer_event`` and its events ride that REPLY, the expiry sweep — which
        runs outside any CALL — passes ``offer_lifecycle`` and they ride the
        outbox. Call it with ``dispatch_lock`` held; returns the dropped row.
        """
        user = self.registry.page_user(page_id)
        self.subscriptions.drop_page(page_id)
        self.drop_page_cache(page_id)
        entry = self.registry.drop_page(page_id)
        announce("drop_page", user=user, page_id=page_id)
        if entry["connection_id"] not in self.connection_items:
            announce("drop_connection", user=user, session_id=entry["connection_id"])
        if user not in self.user_items:
            announce("drop_user", user=user)
        return entry

    def demolish_connection(self, connection_id: str, announce: Callable[..., Any]) -> dict[str, Any]:
        """Take a whole connection off this worker, pages first, user last.

        The pages announce their own drop BEFORE the connection does: the
        surface forgets a connection expecting its pages to be gone already, and
        the order it hears is the order the demolition happened in.
        ``Registry.drop_connection`` takes the user with the last connection of
        it, so that drop is announced too. Same ``announce`` contract as
        ``demolish_page``, same ``dispatch_lock`` hold, same return: the dropped
        row, for the op that answers with its wire view.
        """
        connection = self.connection_items.get(connection_id)
        user = connection["user"]
        for page_id in list(connection["pages"]):
            self.subscriptions.drop_page(page_id)
            self.drop_page_cache(page_id)
            announce("drop_page", user=user, page_id=page_id)
        self.registry.drop_connection(connection_id)
        announce("drop_connection", user=user, session_id=connection_id)
        if user not in self.user_items:
            announce("drop_user", user=user)
        return connection

    @route()
    def drop_page(self, identity: str, page_id: str) -> dict[str, Any]:
        """Drop a page row and announce it on the REPLY of this CALL."""
        with self.dispatch_lock:
            return self.wire_entry(self.demolish_page(page_id, self.offer_event))

    @route()
    def drop_connection(self, identity: str, session_id: str) -> dict[str, Any]:
        """Drop a connection row with its whole cascade — the logout's handle.

        The demolition is ``demolish_connection``'s, in its order — the pages
        first, each announcing its own drop, then the connection, then the user
        when this was its last one — and every announcement rides the REPLY of
        this very CALL, exactly like ``drop_page``. The legacy logout maps here:
        ``register.drop_connection(connection_id, cascade=True)``.
        """
        with self.dispatch_lock:
            if session_id not in self.connection_items:
                raise KeyError(f"drop_connection: unknown connection {session_id!r}")
            return self.wire_entry(self.demolish_connection(session_id, self.offer_event))

    # ------------------------------------------------------------------
    # Expiry: the daemon's cleanup pass, transcribed — and left disarmed.
    # ------------------------------------------------------------------

    def is_guest_connection(self, connection_id: str) -> bool:
        """Whether a connection is still anonymous — the guest rule, by name.

        The daemon's own convention (siteregister.py:716-717), restored: a
        connection is guest while its user name carries the reserved
        ``GUEST_PREFIX`` — whether ``new_connection`` minted it or the
        consumer declared it (issue #14 retired the structural
        user-IS-its-own-id rule, which a consumer naming its guests
        ``guest_<id>`` silently fell out of).
        """
        return self.connection_items.get(connection_id)["user"].startswith(GUEST_PREFIX)

    def sweep_expired(self) -> dict[str, list[str]]:
        """Drop what has been idle too long, announcing every drop on the outbox.

        Transcribed from the daemon's ``expire_pages``/``expire_connection``
        (siteregister.py:709-741): pages first, each against ``page_max_age``
        or ``guest_max_age`` by the guest rule, then the connections that
        survived them against ``connection_max_age`` (``guest_max_age`` for a
        guest) — the three ages are constructor kwargs, the daemon's own
        defaults when not given.
        The connections are snapshot AFTER the pages, so what the page cascade
        already took away is not walked twice.

        These drops are out-of-request lifecycle: there is no CALL to answer, so
        they ride the outbox — the rail of every producer nobody is waiting on.
        ``claim_cleanup`` is not transposed: sticky ownership already gives each
        user exactly one owner, so there is no cross-process claim to arbitrate.

        Sync, under ``dispatch_lock`` — the op INVARIANT: the loop hands it to
        the pool. Returns the ids dropped, by species.
        """
        now = time.time()
        dropped: dict[str, list[str]] = {"pages": [], "connections": []}
        with self.dispatch_lock:
            for page_id in self.page_items.keys():
                page = self.page_items.get(page_id)
                max_age = (
                    self.guest_max_age
                    if self.is_guest_connection(page["connection_id"])
                    else self.page_max_age
                )
                if now - page["last_refresh_ts"] > max_age:
                    self.demolish_page(page_id, self.offer_lifecycle)
                    dropped["pages"].append(page_id)
            for connection_id in self.connection_items.keys():
                connection = self.connection_items.get(connection_id)
                max_age = (
                    self.guest_max_age
                    if self.is_guest_connection(connection_id)
                    else self.connection_max_age
                )
                if now - connection["last_refresh_ts"] > max_age:
                    self.demolish_connection(connection_id, self.offer_lifecycle)
                    dropped["connections"].append(connection_id)
        return dropped

    async def sweep_loop(self) -> None:
        """Run the sweep every ``sweep_interval`` seconds, off the loop.

        Started only when the interval is set: DISARMED by default, and
        deliberately so — without a presence signal from the browser an idle
        page is indistinguishable from a silent one, and the sweep would kill
        pages that are merely quiet. The browser rail arms it.
        """
        while True:
            await asyncio.sleep(self.sweep_interval)
            await self.pool.run(self.sweep_expired)

    # ------------------------------------------------------------------
    # The move: evict packages a whole user slice and spends it; install
    # rebuilds it in the ONE order that works. Both halves run under the lock.
    # ------------------------------------------------------------------

    def pack_connections(self, user: str) -> dict[str, dict[str, Any]]:
        """Package every connection row of ``user`` for the move.

        A connection row carries its live store and no collector, so packing is
        the row minus what the destination rebuilds — the store travels inside
        the pickled blob and lands hydrated. Nothing is dropped here:
        the ``drop_user`` that ends the eviction takes the connections with it,
        pages and all.
        """
        return {
            connection_id: {
                key: value
                for key, value in self.connection_items.get(connection_id).items()
                if key not in MOVE_CONNECTION_REBUILT_FIELDS
            }
            for connection_id in self.user_items.get(user)["connections"]
        }

    def evict_pages(self, user: str) -> dict[str, dict[str, Any]]:
        """Package every page of ``user`` for the move and take them off here.

        Capture ceases FIRST — a change landing after the drain would stay
        behind in a collector nobody holds — and only then is everything pending
        drained into the parcel, in the three-species shape ``collect_page``
        already gives it. What travels is the whole row minus what the
        destination rebuilds, plus the two drained species under their own keys.
        The local subscription index forgets the page here: a stale entry would
        resolve a destination for a page this worker no longer has. The cache
        observer is unsubscribed in the same breath, before the drain: the store
        travels, and a subscription of THIS worker must not travel with it.

        The pages are reached by walking the tree — the user's ``connections``,
        each connection's ``pages`` (a copy, it is emptied as we go) — and each
        departure discards its id from that set, so the ``drop_user`` closing
        the eviction finds no page it has already handed over.
        """
        packaged = {}
        for connection_id in self.user_items.get(user)["connections"]:
            connection = self.connection_items.get(connection_id)
            for page_id in list(connection["pages"]):
                page = self.page_items.get(page_id)
                self.registry.detach_page(page)
                self.drop_page_cache(page_id)
                pending = self.collect_page(page_id)
                self.page_items.drop(page_id)
                connection["pages"].discard(page_id)
                self.subscriptions.drop_page(page_id)
                packaged[page_id] = {
                    **{k: v for k, v in page.items() if k not in MOVE_REBUILT_FIELDS},
                    "pending_datachanges": pending["datachanges"],
                    "pending_dbevents": pending["dbevents"],
                }
        return packaged

    def encode_user(self, user: str) -> str:
        """Seal the whole slice of ``user`` into its encoded wire form and spend it here.

        The one road out of a worker, and the two commanded departures —
        ``evict_user`` toward another worker, ``freeze_user`` toward a file —
        are its only callers: the parcel is the user entry without its live fields, the store
        itself, every connection row, every page drained on the way out — and
        it leaves nothing behind, because a slice that is on the wire must be
        nowhere else. The order is the one ``evict_pages`` describes: the pages
        come off BEFORE the Bags are pickled, so no collector of this worker is
        watching what travels.
        """
        entry = self.user_items.get(user)
        connections = self.pack_connections(user)
        pages = self.evict_pages(user)
        blob = {
            "user": user,
            "user_entry": {k: v for k, v in entry.items() if k not in LIVE_ROW_FIELDS},
            "user_store": entry["store"],
            "connections": connections,
            "pages": pages,
        }
        self.registry.drop_user(user)
        return base64.b64encode(pickle.dumps(blob)).decode("ascii")

    @route()
    def evict_user(self, identity: str) -> dict[str, Any]:
        """Hand the slice of ``identity`` up to the commander and forget it here.

        The commanded move, transcribed from the legacy ``/evict_user``: the
        commander orders the departure — a move, a rebalance, a shutdown dump —
        and the worker answers with the parcel. OPERATIONAL, so it shapes NO
        event: the surface is the one that asked, and it learns the outcome
        from this very reply. Since the login stopped shipping (ratified
        2026-08-12) this is the ONLY way a slice leaves a living worker, and
        ``freeze_user`` is its sibling toward a file rather than a worker.
        """
        with self.dispatch_lock:
            if self.user_items.get(identity) is None:
                raise KeyError(f"evict_user: unknown user {identity!r}")
            return {"encoded": self.encode_user(identity)}

    @route()
    def freeze_user(self, identity: str) -> dict[str, Any]:
        """Seal the slice of ``identity`` into the parcel the freezer parks on disk.

        The sibling of ``evict_user``, same one road out: the parcel is
        ``encode_user``'s, field for field, and the slice is spent here the
        moment this answers. What differs is the destination the commander
        gives it — a file instead of another worker — so the two ops can
        diverge without the freezer riding the move's own surface.

        Sync, and that is the whole of the off-loop discipline: ``execute``
        runs a sync op on a pool thread through ``run_in_executor``, so both
        the seal under ``dispatch_lock`` and the pickle of the user's Bags
        happen off the loop. OPERATIONAL, so it shapes no event.
        """
        with self.dispatch_lock:
            if self.user_items.get(identity) is None:
                raise KeyError(f"freeze_user: unknown user {identity!r}")
            return {"encoded": self.encode_user(identity)}

    def install_connection(self, user: str, connection_id: str, packed: dict[str, Any]) -> None:
        """Rebuild one packaged connection row under ``user``.

        The connections land BEFORE their pages: a page brings its connection
        into being when it finds none, and a connection born that way would lose
        every field it carried across the move.
        """
        self.registry.new_connection(connection_id, user=user, **packed)

    def install_page(self, user: str, page_id: str, packed: dict[str, Any]) -> None:
        """Rebuild one packaged page under ``user``, in the mandatory order.

        The Bag came hydrated out of the parcel, so the collector ``new_page``
        attaches to it captures nothing — attaching one BEFORE the hydration
        would have turned every arrived node into a fresh change. The cache
        observer is attached here for the same reason the source removed it: it
        is a subscription of the worker that holds the page, so the destination
        makes its own. What the arrived store already cached is re-recorded by
        the next write to it, as it is in the daemon after a load.
        Then the subscriptions live again: the page's own prefixes re-filter its
        collector, the store prefixes rebuild ``user_view`` on the user's
        arrived Bag, the tables rebuild both maps of
        the index. The pendings are re-deposited LAST and verbatim — ``append``
        keeps the producer's ``change_ts`` and assigns a fresh local
        ``change_idx``, so the destination drains them in the order they left.
        """
        fields = {key: value for key, value in packed.items() if key not in MOVE_REPLAYED_KEYS}
        page = self.registry.new_page(page_id, user=user, **fields)
        self.attach_cache_observer(page_id, page["store"])
        for prefix in packed["subscribed_paths"]:
            page["subscribed_paths"].add(prefix)
            page["collector"].subscribe_path(prefix)
        for prefix in packed["store_subscriptions"]:
            self.registry.subscribe_store_path(page_id, prefix)
        for table in packed["table_subscriptions"]:
            page["table_subscriptions"].add(table)
            self.subscriptions.subscribe(page_id, table)
        for change in packed["pending_datachanges"]:
            page["collector"].append(change)
        page["dbevents"].extend(packed["pending_dbevents"])

    def adopt_carried_store(self, user: str, store: Any) -> None:
        """Put the parcel's own store under a resident entry, watchers and all.

        The wake's exception to the JOIN, and the reason it is safe: a frozen
        user had no live entry anywhere, so a resident found at the destination
        is minutes old against days of hibernated state. Every page already
        watching the old Bag is re-attached exactly as
        ``change_connection_user`` re-attaches on a login — a fresh collector on
        the new Bag with the same prefixes, re-deposited with everything the old
        one still held — so no captured change is lost in the swap.
        """
        entry = self.user_items.get(user)
        entry["store"] = store
        for connection_id in entry["connections"]:
            for page_id in self.connection_items.get(connection_id)["pages"]:
                page = self.page_items.get(page_id)
                view = page["user_view"]
                if view is None:
                    continue
                view.detach()
                fresh = self.registry.new_collector(
                    store, paths=set(page["store_subscriptions"])
                )
                for change in view.changes:
                    fresh.append(change)
                page["user_view"] = fresh

    @route()
    def add_user(self, identity: str, encoded: str, parcel_wins: bool = False) -> dict[str, Any]:
        """Install a moved user's slice from its encoded wire form — the rebirth.

        Operational, like every install primitive: the commander orders it, so
        it needs no event back — the source already spent its copy answering
        the evict. The item arrives whole, so its identity and every field it
        carried survive the move; ``identity`` is the routing key the CALL was
        addressed with and must match the carried user.

        The room is ready when this returns, and the whole slice is what makes
        it ready: the user's store first, because a page's ``user_view`` is a
        collector on that very Bag, then the connections, then every page
        rebuilt in the ordered way ``install_page`` describes.

        **The install JOINS.** A user already living here is not re-born: the
        resident entry and its live store ARE the truth, and the blob's own copy
        of them is discarded — a second connection of the same user arrives to
        join what is already open, so the arriving pages' ``user_view``
        collectors attach to the resident Bag. Only the connections and the
        pages are ever installed twice over; the user is installed once.

        **Unless the parcel wins.** ``parcel_wins`` inverts that one rule for
        the wake of a hibernated user, and for nothing else: the commander
        knows the identity had no live entry anywhere, so it declares the
        carried store the truth and ``adopt_carried_store`` puts it under the
        resident entry, re-attaching whatever was watching the old Bag. The
        entry itself stays the resident's — it is the one the open connection
        already answers through.
        """
        blob = pickle.loads(base64.b64decode(encoded))
        user = blob["user"]
        if user != identity:
            raise ValueError(f"add_user: slice of {user!r} addressed to {identity!r}")
        with self.dispatch_lock:
            entry = self.user_items.get(user)
            joined = entry is not None
            if entry is None:
                carried = {k: v for k, v in blob["user_entry"].items() if k != "register_item_id"}
                entry = self.registry.new_user(user, store=blob["user_store"], **carried)
            elif parcel_wins:
                self.adopt_carried_store(user, blob["user_store"])
            for connection_id, packed in blob["connections"].items():
                self.install_connection(user, connection_id, packed)
            for page_id, packed in blob["pages"].items():
                self.install_page(user, page_id, packed)
            # ``joined`` is the caller's anomaly signal: a commanded move never
            # expects a resident at its destination, and a join there means the
            # parcel's own entry and store yielded to whoever got in first.
            return {**self.wire_entry(entry), "joined": joined}
