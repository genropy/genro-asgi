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
- ``channel`` — the member face of the wire (a :class:`WorkerChannelClient`
  over a socket, or a :class:`LocalChannel` in the single role): the same API
  either way, injected by whoever builds the worker.

**One envelope per CALL: causal attribution.** ``service_call`` opens a sink —
an instance ContextVar holding a fresh list — for the CALL it is answering, and
``offer_event`` appends to whichever sink its context sees (a sync handler runs
on a pool thread with the context copied, so it appends to the same list).
``send_reply`` carries exactly that list in ``data["events"]``: a REPLY reports
the lifecycle the answered call CAUSED, nothing else. The commander folds it in
the caller's own coroutine BEFORE reading the result, so the routing picture is
already updated when the response is released. Each CALL is SERVED on its own
task — ``create_task`` copies the context, so the sink of a CALL in flight is
its own list and two CALLs never see each other's events; a lifecycle op
outside any CALL is impossible and says so.

**The outbox is the async rail, and the exchange is one of its producers.** ``Outbox``,
``notify_sender`` and ``sender_loop`` are the transport of the cross-worker
traffic (design D4): a datachange whose target is not here rides them up to the
commander as an EVENT. The lifecycle never does — it rides the REPLY of the CALL
that caused it.

**The login pushes the user out.** ``change_connection_user`` re-labels the
CONNECTION onto the logged-in user — a mutation, never a re-key: keys, live
stores and collectors survive it, with ONE declared exception: the anonymous
user entry claiming its first real identity is transferred whole onto the new
key, store included — and then, under the very same lock, packages
the user's whole slice, DROPS it from ``user_items`` and offers the login event
with that ``package`` riding on it: the worker spends its copy and forgets
(legacy ``evict_user``). Nothing is left here for a second step to collect: the
commander installs the package on the worker it decides the user belongs to,
this one included. ONE login does not push: the one onto a user this worker
already hosts. There the registry's join is everything — the connection is
linked to the resident entry and the event carries no ``package`` — so a
resident's pages never leave the worker they are being served on.

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
cannot. Nothing is pushed: a change for a page that never calls waits in its
collector. The op outcome does not gate the drain, and a CALL addressing no
page carries neither key.

**The addressed write has three tiers, and one switch.** ``set_datachange``,
``reset_datachanges`` and ``drop_datachanges`` all address a target that may or
may not be here, and ``route_datachange`` is the switch: a target this worker
holds is applied at once (tier 2 — no channel traffic), anything else ascends
on the outbox to the commander, which resolves and pushes it back down as a
``DATACHANGE_IN_PATH`` batch (tier 3). Tier 1 needs no op at all: a page writing
its own store writes the Bag. A filtered broadcast always ascends — the surface
that knows every page is up there.

**STATE applies as a write, SIGNAL applies as a deposit.** ``kind`` says which:
``page_store``/``user_store`` are state, so they land through
``apply_forwarded`` (a real Bag write, ``_original_ts`` carried); ``page`` is a
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
``{identity, http: {...}}`` form is accepted by the protocol and answered with
an explicit error REPLY: there is no environ synthesizer until phase B.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import logging
import pickle
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
from .global_store import (
    GLOBAL_CHANGES_PATH,
    GLOBAL_GRANT_PATH,
    GLOBAL_SNAPSHOT_PATH,
    CapturingGlobalStore,
    GlobalStore,
    GlobalStoreLease,
)
from .register import Register
from .register_registry import RegisterRegistry
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
STATE_KINDS = frozenset({"page_store", "user_store"})

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
    {"store_subscriptions", "table_subscriptions", "pending_datachanges", "pending_dbevents"}
)

# The connection-row fields the rebirth builds itself: the reserved key, the
# user the destination re-creates the row under, and the ``pages`` edge set the
# arriving pages fill in as they land. A connection row holds no live object at
# all, so everything else in it travels verbatim.
MOVE_CONNECTION_REBUILT_FIELDS = frozenset({"register_item_id", "user", "pages"})


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
    ) -> None:
        """Args:
        name: the worker's channel name (already typed, e.g. ``W:w1``).
        channel: the member face of the wire; ``attach_channel`` may set it later.
        max_threads: ``WorkPool`` size for the sync op handlers.
        """
        self.name = name
        self.registry = self.build_registry()
        self.outbox = Outbox(self)
        self.pool = WorkPool(self, max_threads)
        # Reentrant: the subscription index takes this very lock, so an index
        # change and the row change it belongs to are ONE critical section even
        # though the op already holds it.
        self.dispatch_lock = threading.RLock()
        self.subscriptions = SubscriptionIndex(self.dispatch_lock)
        # The global store as this worker sees it: a replica, read locally and
        # written only by what the commander pushes down.
        self.global_replica = GlobalStore()
        # The lock requests parked on their grant, by request id.
        self.global_grants: dict[str, asyncio.Future[Any]] = {}
        self.last_seq = 0
        self.logger = logging.getLogger(__name__)
        self.channel: Any = None
        # The causal sink: the events produced BY the CALL being answered in
        # this context. Instance-owned (never module level), so two CALLs in
        # flight fill two distinct lists.
        self._call_events: ContextVar[list[dict[str, Any]] | None] = ContextVar(
            "call_events", default=None
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._outbox_ready = asyncio.Event()
        self._sender_task: asyncio.Task[None] | None = None
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
    def op_names(self) -> set[str]:
        """The op names this worker routes (its ``@route`` methods)."""
        return set(self.route.nodes(lazy=True).get("entries", {}))

    def attach_channel(self, channel: Any) -> None:
        """Wire an endpoint: its frames come here, its sender wakes on the outbox."""
        self.channel = channel
        channel.on_message = self.handle_frame
        self.outbox.notify = self.notify_sender

    async def start(self) -> None:
        """Start the async sender on the running loop."""
        self._loop = asyncio.get_running_loop()
        self._sender_task = asyncio.create_task(self.sender_loop())

    async def shutdown(self) -> None:
        """Deliberate stop: cancel the sender and the CALLs in flight, then close.

        The in-flight services die with their REPLYs unsent: the stop is
        deliberate and the channel closes anyway, so nobody is left to read
        them.
        """
        tasks = [
            task
            for task in (self._sender_task, *self._service_tasks)
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
        if self.channel is not None:
            await self.channel.close()
        self.pool.shutdown(wait=False)

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
        """Open this CALL's causal sink, answer it, then close the sink.

        The sink is what the REPLY carries: the lifecycle this very call
        produced. Held on the instance ContextVar, so a concurrent CALL — on its
        own task context — fills its own list and the two never mix.
        """
        token = self._call_events.set([])
        try:
            await self.answer_call(frame)
        finally:
            self._call_events.reset(token)

    async def answer_call(self, frame: Frame) -> None:
        """Dispatch one CALL and reply with its result, or with its failure.

        A CALL whose kwargs carry a ``page_id`` is page-addressed: its REPLY is
        also the page's pull cycle, so the drain rides it — see ``send_reply``.
        """
        payload = frame.data or {}
        if "http" in payload:
            await self.send_reply(frame, error="http CALL form is unsupported until phase B")
            return
        page_id = (payload.get("kwargs") or {}).get("page_id")
        try:
            result = await self.execute(frame.path, payload)
        except Exception as exc:
            self.logger.exception("%s: CALL %s failed", self.name, frame.path)
            await self.send_reply(frame, error=f"{type(exc).__name__}: {exc}", page_id=page_id)
            return
        await self.send_reply(frame, result=result, page_id=page_id)

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
        """Answer a CALL, carrying the events that CALL caused for the fold.

        The envelope is causal: the commander folds exactly what this call
        produced, and the delivery is single — the send IS the delivery over UDS
        as over a queue, so there is nothing to ack and nothing to replay.

        Delivery to the client is PULL, on the page's own request/response
        cycle: when the CALL is page-addressed and that page is still
        registered here, its drain travels under ``DELIVERY_KEYS`` — the two
        species keep their own key, never merged. The outcome of the op does not
        gate it: what is pending for the page is pending either way. A page the
        CALL itself dropped has nothing left to pull, and a CALL that addresses
        no page carries neither key.
        """
        data: dict[str, Any] = {"events": list(self.call_events)}
        if error is not None:
            data["error"] = error
        else:
            data["result"] = result
        if page_id is not None and self.page_items.get(page_id) is not None:
            data.update(self.wire_delivery(page_id))
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

        The lifecycle never comes through here — it rides the REPLY envelope.
        What does is the ascending exchange: a message whose target is on another
        worker, for the commander to resolve.
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

    def occupancy_report(self) -> dict[str, Any]:
        """The counters the commander archives: what the registers can answer."""
        return {
            "worker": self.name,
            "users": len(self.user_items),
            "pages": len(self.page_items),
            "pending": self.outbox.pending(),
            "seq": self.last_seq,
        }

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

        The single drain point: the page's own capture-all collector and its
        ``user_view`` (when it has one) are drained together and merged by
        ``change_ts`` — the sort is stable, so two changes stamped alike keep
        the order they were collected in. The dbevents are their own species
        and travel in their own key, never dressed as datachanges.

        Raises ``KeyError`` if ``page_id`` is not registered here.
        """
        page = self.page_items.get(page_id)
        if page is None:
            raise KeyError(f"collect_page: unknown page {page_id!r}")
        datachanges = page["collector"].drain()
        if page["user_view"] is not None:
            datachanges.extend(page["user_view"].drain())
        datachanges.sort(key=lambda change: change["change_ts"])
        dbevents = page["dbevents"]
        page["dbevents"] = []
        return {"datachanges": datachanges, "dbevents": dbevents}

    def wire_delivery(self, page_id: str) -> dict[str, Any]:
        """The drain of one page, encoded for the wire — one key per species.

        A change is not a JSON value: it carries the node's own value (a Bag when
        the write created an intermediate node) and a ``change_ts`` datetime. So
        each species travels TYTX-encoded, the same vehicle the move package uses
        for a store — the reader hydrates it with ``from_tytx``. The frame codec
        stays untouched.
        """
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
        ascends on the outbox and the commander, which alone sees every page,
        resolves it. A filtered broadcast always ascends for that same reason.
        """
        if message["filters"] is None and self.holds_target(message):
            self.apply_datachange(message)
            return
        self.outbox.offer(self.shape_exchange(message))

    def target_row(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """The register row a message addresses, or None when it is not here.

        ``kind`` chooses the register: only ``user_store`` names a user, every
        other kind names a page.
        """
        register = self.user_items if message["kind"] == "user_store" else self.page_items
        return register.get(message["target"])

    def holds_target(self, message: dict[str, Any]) -> bool:
        """Whether the message's target is registered on this worker."""
        return self.target_row(message) is not None

    def apply_datachange(self, message: dict[str, Any]) -> None:
        """Apply one message to a target of this worker. Under ``dispatch_lock``.

        The state/signal split lands here: a store address is a real Bag write,
        a page address is a deposit on that page's collector. The parcel is
        decoded at this single point — it travelled TYTX from wherever it was
        produced.
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
            row["collector"].append(from_tytx(message["change"], "json"))

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
        **addressing: Any,
    ) -> dict[str, Any]:
        """Write a change toward a target that may live anywhere.

        ``change`` is the TYTX-encoded change dict, ``kind`` says what ``target``
        names (a page store, a user store, or the page itself), and ``filters``
        is the alternative address: the broadcast the commander resolves over
        every page it knows. ``addressing`` absorbs the caller's own ``page_id``
        — the pull cycle of the CALL, never the target of the write.
        """
        with self.dispatch_lock:
            message = self.exchange_message(
                "set_datachange", kind=kind, target=target, filters=filters, change=change
            )
            self.route_datachange(message)
        return {"kind": kind, "target": target, "filters": filters}

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
    ) -> dict[str, Any]:
        """Subscribe (or unsubscribe) the CALLING page to a table's events.

        ``page_id`` is the caller's own page here — the subscriber is whoever
        asks — so the same field that names the pull cycle of this CALL names
        the subscription's owner, and there is no target to address.

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
        """
        deposits = [
            self.dbevent_deposit(table, batch, page_id, reason)
            for table, batch in (dbevents or {}).items()
            if batch
        ]
        with self.dispatch_lock:
            for deposit in deposits:
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

    def deposit_dbevent(self, page_id: str, deposit: dict[str, Any]) -> None:
        """Append one deposit to a page's own pending list. Under ``dispatch_lock``.

        A page this worker does not hold — dropped, or moved while the batch was
        on the wire — loses the deposit with a debug log: a dbevent is a signal.
        """
        page = self.page_items.get(page_id)
        if page is None:
            self.logger.debug("%s: dbevent dropped, no page %r", self.name, page_id)
            return
        page["dbevents"].append(deposit)

    async def apply_dbevents_in(self, batch: list[dict[str, Any]]) -> None:
        """Apply one descending dbevents batch — the arrival of its own pipe.

        Off the loop, like the exchange side: every item takes ``dispatch_lock``.
        """
        try:
            await self.pool.run(functools.partial(self.apply_dbevents_batch, batch))
        except Exception:
            self.logger.exception("%s: dbevents_in batch failed", self.name)

    def apply_dbevents_batch(self, batch: list[dict[str, Any]]) -> None:
        """Deposit a whole descending batch under one lock, page by page."""
        with self.dispatch_lock:
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
        ``Registry.new_connection`` gives it the naked session id as its user
        and brings that guest user entry into being with it — the surface hears
        the cascade in the order it happened, the ``new_user`` it really is and
        then the connection.
        """
        with self.dispatch_lock:
            unseen_user = fields.get("user", identity) not in self.user_items
            entry = self.registry.new_connection(identity, **fields)
            if unseen_user:
                self.offer_event("new_user", user=entry["user"])
            self.offer_event("new_connection", user=entry["user"], session_id=identity)
            return self.wire_entry(entry)

    @route()
    def change_connection_user(self, identity: str, user: str, **fields: Any) -> dict[str, Any]:
        """Re-label the connection ``identity`` onto the logged-in ``user``, then push it out.

        The login transition: the sticky key of the CONNECTION stops being the
        anonymous one (its own session id) and becomes the root avatar identity.
        Nothing dies at login — ``Registry.change_connection_user`` mutates
        the live connection row; on a first login the anonymous user entry is
        transferred whole onto the new key (store included, the registry's
        declared divergence), otherwise the old user leaves only once its
        ``connections`` set is empty.

        **A resident login links, it never ships.** When this worker ALREADY
        hosts the target user the registry's join is the whole login: the
        connection is linked to the resident entry, its pages' ``user_view`` is
        re-attached to the resident store, the orphaned guest dies — and nothing
        travels. No package, no drop, and the login event goes up WITHOUT the
        ``package`` key, which is how the commander reads "this user is at home,
        there is no room to make". The resident's other connections and their
        pages are never taken off the register, so no traffic addressed to them
        can fall into an eviction window: there is none.

        Otherwise the re-labelled slice LEAVES this worker in the same locked
        mutation: it is packaged onto the event and dropped here, so the
        commander has both keys and the baggage in one message and installs the
        user wherever it decides. That is the road of a user BORN here by this
        very login too — the commander must stay free to place it anywhere. The
        returned entry is the snapshot the caller logged in with.

        The pages are evicted BEFORE the Bags are pickled, and that order is
        load-bearing: their ``user_view`` collectors are attached to the user's
        store, so detaching them is what leaves the Bag with nothing watching it
        when it is serialized. The baggage is a sealed Python-to-Python parcel
        nobody reads en route — the vehicle is pickle, base64 inside the JSON
        envelope — and pickling IS the snapshot: the blob needs no copy of its
        own.
        """
        with self.dispatch_lock:
            connection = self.connection_items.get(identity)
            if connection is None:
                raise KeyError(f"change_connection_user: unknown connection {identity!r}")
            previous_user = connection["user"]
            resident = user in self.user_items
            self.registry.change_connection_user(identity, user, **fields)
            entry = self.user_items.get(user)
            if resident:
                self.offer_event(
                    "change_connection_user",
                    user=user,
                    previous_user=previous_user,
                    session_id=identity,
                )
                return self.wire_entry(entry)
            connections = self.pack_connections(user)
            pages = self.evict_pages(user)
            blob = {
                "user": user,
                "user_entry": {k: v for k, v in entry.items() if k not in LIVE_ROW_FIELDS},
                "user_store": entry["store"],
                "connections": connections,
                "pages": pages,
            }
            package = base64.b64encode(pickle.dumps(blob)).decode("ascii")
            self.registry.drop_user(user)
            self.offer_event(
                "change_connection_user",
                user=user,
                previous_user=previous_user,
                session_id=identity,
                package=package,
            )
            return self.wire_entry(entry)

    @route()
    def drop_user(self, identity: str) -> dict[str, Any]:
        """Drop the user entry (and its pages) and announce it.

        The pages to forget in the subscription index are collected by walking
        the tree down — the user entry's ``connections``, each connection's
        ``pages`` — before the registry demolishes it.
        """
        with self.dispatch_lock:
            entry = self.user_items.get(identity)
            if entry is None:
                raise KeyError(f"drop_user: unknown user {identity!r}")
            for connection_id in entry["connections"]:
                for page_id in self.connection_items.get(connection_id)["pages"]:
                    self.subscriptions.drop_page(page_id)
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
            if unseen_user:
                self.offer_event("new_user", user=identity)
            if unseen_connection:
                self.offer_event("new_connection", user=identity, session_id=entry["connection_id"])
            self.offer_event(
                "new_page", user=identity, page_id=page_id, session_id=entry["connection_id"]
            )
            return self.wire_entry(entry)

    @route()
    def drop_page(self, identity: str, page_id: str) -> dict[str, Any]:
        """Drop a page row and announce it — with the cascade up the chain.

        ``Registry.drop_page`` takes the connection away with the last page of
        it, and the user with the last connection of that user, so the surface
        must hear about those too: the cascade is announced, in the order it
        climbs, as the ``drop_connection`` and ``drop_user`` it really is, right
        after the page event.

        The owner is resolved BEFORE the drop: it is derived through the chain,
        and the chain is exactly what the cascade may tear down.
        """
        with self.dispatch_lock:
            user = self.registry.user_of_page(page_id)
            self.subscriptions.drop_page(page_id)
            entry = self.registry.drop_page(page_id)
            self.offer_event("drop_page", user=user, page_id=page_id)
            if entry["connection_id"] not in self.connection_items:
                self.offer_event("drop_connection", user=user, session_id=entry["connection_id"])
            if user not in self.user_items:
                self.offer_event("drop_user", user=user)
            return self.wire_entry(entry)

    # ------------------------------------------------------------------
    # The move: evict packages a whole user slice and spends it; install
    # rebuilds it in the ONE order that works. Both halves run under the lock.
    # ------------------------------------------------------------------

    def pack_connections(self, user: str) -> dict[str, dict[str, Any]]:
        """Package every connection row of ``user`` for the move.

        A connection row is pure metadata — no store, no collector — so packing
        is the row minus what the destination rebuilds. Nothing is dropped here:
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
        resolve a destination for a page this worker no longer has.

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

    def install_connection(self, user: str, connection_id: str, packed: dict[str, Any]) -> None:
        """Rebuild one packaged connection row under ``user``.

        The connections land BEFORE their pages: a page brings its connection
        into being when it finds none, and a connection born that way would lose
        every field it carried across the move.
        """
        self.registry.new_connection(connection_id, user=user, **packed)

    def install_page(self, user: str, page_id: str, packed: dict[str, Any]) -> None:
        """Rebuild one packaged page under ``user``, in the mandatory order.

        The Bag came hydrated out of the parcel, so the capture-all collector
        ``new_page`` attaches to it captures nothing — attaching one BEFORE the
        hydration would have turned every arrived node into a fresh change.
        Then the subscriptions live again: the store prefixes rebuild
        ``user_view`` on the user's arrived Bag, the tables rebuild both maps of
        the index. The pendings are re-deposited LAST and verbatim — ``append``
        keeps the producer's ``change_ts`` and assigns a fresh local
        ``change_idx``, so the destination drains them in the order they left.
        """
        fields = {key: value for key, value in packed.items() if key not in MOVE_REPLAYED_KEYS}
        page = self.registry.new_page(page_id, user=user, **fields)
        for prefix in packed["store_subscriptions"]:
            self.registry.subscribe_store_path(page_id, prefix)
        for table in packed["table_subscriptions"]:
            page["table_subscriptions"].add(table)
            self.subscriptions.subscribe(page_id, table)
        for change in packed["pending_datachanges"]:
            page["collector"].append(change)
        page["dbevents"].extend(packed["pending_dbevents"])

    @route()
    def add_user(self, identity: str, blob: dict[str, Any]) -> dict[str, Any]:
        """Install a moved user's slice from the decoded blob — the rebirth.

        Operational, like every install primitive: the commander orders it, so
        it needs no event back — the source already spent its copy on the login
        event. The item arrives whole, so its identity and every field it
        carried survive the move; ``identity`` is the routing key the CALL was
        addressed with and must match the blob's own user.

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
        """
        user = blob["user"]
        if user != identity:
            raise ValueError(f"add_user: package of {user!r} addressed to {identity!r}")
        with self.dispatch_lock:
            entry = self.user_items.get(user)
            if entry is None:
                carried = {k: v for k, v in blob["user_entry"].items() if k != "register_item_id"}
                entry = self.registry.new_user(user, store=blob["user_store"], **carried)
            for connection_id, packed in blob["connections"].items():
                self.install_connection(user, connection_id, packed)
            for page_id, packed in blob["pages"].items():
                self.install_page(user, page_id, packed)
            return self.wire_entry(entry)

    @route()
    def install_package(self, identity: str, package: str) -> dict[str, Any]:
        """Decode a transport package and install it — the descending move."""
        return self.add_user(identity, pickle.loads(base64.b64decode(package)))
