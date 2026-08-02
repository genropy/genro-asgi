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
- ``outbox`` — the FIFO the async sender drains; idle infrastructure in 2a (no
  producer feeds it), kept for the cleanup and cross-worker traffic to come.
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

**The outbox is idle infrastructure.** ``Outbox``, ``notify_sender`` and
``sender_loop`` stay wired with no producer: they are the transport of the
cleanup and cross-worker traffic to come (design D4). Nothing in 2a offers to
them, so the sender never wakes.

**The login pushes the user out.** ``change_connection_user`` re-keys the entry
and then, under the very same lock, packages it, DROPS it from ``user_items``
and offers the login event with that ``package`` riding on it — the worker
spends its copy and forgets (legacy ``evict_user``). Nothing is left here for a
second step to collect: the commander installs the package on the worker it
decides the user belongs to, this one included.

**Operational signals are ANSWERED, never pushed.** ``occupancy`` is an async
op like any other: the commander probes it and the worker replies with the
counters its registers can answer. Because the answer comes from the loop, one
exchange carries both readings — the data, and the proof that this worker is
still alive to produce it. The worker owns no clock for it.

**Op vocabulary.** ``LIFECYCLE_OPS``/``STORE_OPS``/``POST_OPS``/
``EXCHANGE_OPS`` are transcribed whole from the legacy worker: they are the
reserved protocol names. In 2a only the user lifecycle ops are active
(``new_user``, ``change_connection_user``, ``drop_user``) plus the two install
primitives, which are operational (they mutate on the commander's own order,
so they shape no event). Everything else is a reserved name with no handler.

**CALL forms.** ``data`` is ``{identity, kwargs}`` — ``identity`` is the
sticky key and reaches the handler as its first argument. The
``{identity, http: {...}}`` form is accepted by the protocol and answered with
an explicit error REPLY: there is no environ synthesizer until phase B.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import functools
import logging
import pickle
import threading
from contextvars import ContextVar
from typing import Any, Callable

from genro_routes import RoutingClass, route

from ..channel.client import ChannelClient
from ..channel.frame import Frame
from ..channel.hub import CALL_METHOD, EVENT_METHOD, REPLY_METHOD
from ..pool import WorkPool
from .register import Register
from .register_registry import RegisterRegistry

__all__ = [
    "EXCHANGE_OPS",
    "LIFECYCLE_OPS",
    "OP_PATH_PREFIX",
    "POST_OPS",
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

# The ascending-operational commands: global store writes. Reserved names — the
# GlobalStore is out of 2a scope.
STORE_OPS = frozenset({"store_set", "store_del"})

# The POST commands: table subscriptions and db-event notifications. Reserved names —
# the subscription surfaces arrive with the pages (2b).
POST_OPS = frozenset({"subscribeTable", "notifyDbEvents"})

# The datachange EXCHANGE commands: applicative writes toward a page (or a user's
# pages). Reserved names — the switch model arrives with the pages (2b).
EXCHANGE_OPS = frozenset({"set_datachange", "reset_datachanges", "drop_datachanges"})

#: Routing prefix of an op CALL/EVENT path: ``/op/new_user`` carries op ``new_user``.
OP_PATH_PREFIX = "/op/"


class Outbox:
    """FIFO of shaped lifecycle events, acked per-seq by the drainer.

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
        self.registry = RegisterRegistry()
        self.outbox = Outbox(self)
        self.pool = WorkPool(self, max_threads)
        self.dispatch_lock = threading.Lock()
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

    @property
    def user_items(self) -> Register:
        """The register of the users this worker holds."""
        return self.registry.user_items

    @property
    def page_items(self) -> Register:
        """The register of the pages this worker holds (inert until 2b)."""
        return self.registry.page_items

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

        Inbound EVENTs are the commander's descending pushes — no consumer in
        2a (the store and datachange fan-outs arrive with their surfaces).
        """
        if frame.method == CALL_METHOD:
            task = asyncio.create_task(self.guarded_service(frame))
            self._service_tasks.add(task)
            task.add_done_callback(self._service_tasks.discard)
        elif frame.method == EVENT_METHOD:
            self.logger.debug("%s: no consumer for EVENT %s", self.name, frame.path)
        else:
            self.logger.warning("%s: unexpected envelope %s", self.name, frame.method)

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
        """Dispatch one CALL and reply with its result, or with its failure."""
        payload = frame.data or {}
        if "http" in payload:
            await self.send_reply(frame, error="http CALL form is unsupported until phase B")
            return
        try:
            result = await self.execute(frame.path, payload)
        except Exception as exc:
            self.logger.exception("%s: CALL %s failed", self.name, frame.path)
            await self.send_reply(frame, error=f"{type(exc).__name__}: {exc}")
            return
        await self.send_reply(frame, result=result)

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

    async def send_reply(self, frame: Frame, *, result: Any = None, error: Any = None) -> None:
        """Answer a CALL, carrying the events that CALL caused for the fold.

        The envelope is causal: the commander folds exactly what this call
        produced, and the delivery is single — the send IS the delivery over UDS
        as over a queue, so there is nothing to ack and nothing to replay.
        """
        data: dict[str, Any] = {"events": list(self.call_events)}
        if error is not None:
            data["error"] = error
        else:
            data["result"] = result
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

        Idle in 2a: the lifecycle rides the REPLY envelope and nothing offers to
        the outbox, so this runs only for the traffic that will come.
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
            return entry

    @route()
    def change_connection_user(self, identity: str, user: str, **fields: Any) -> dict[str, Any]:
        """Re-key the entry of ``identity`` to the logged-in ``user``, then push it out.

        The login transition: the sticky key stops being the anonymous one
        (a session id) and becomes the root avatar identity. Re-keying is a drop
        plus a create at ``user_items`` level — pages follow their user in 2b,
        when the worker owns any.

        The re-keyed entry then LEAVES this worker in the same locked mutation:
        it is packaged onto the event and dropped here, so the commander has
        both keys and the baggage in one message and installs the user wherever
        it decides. The returned entry is the snapshot the caller logged in with.
        """
        with self.dispatch_lock:
            entry = self.user_items.get(identity)
            if entry is None:
                raise KeyError(f"change_connection_user: unknown identity {identity!r}")
            if user == identity:
                entry = self.user_items.update(identity, **fields)
            else:
                carried = {k: v for k, v in entry.items() if k != "register_item_id"}
                self.user_items.drop(identity)
                entry = self.registry.new_user(user, **{**carried, **fields})
            blob = {"user": user, "user_entry": copy.deepcopy(entry)}
            package = base64.b64encode(pickle.dumps(blob)).decode("ascii")
            self.registry.drop_user(user)
            self.offer_event(
                "change_connection_user", user=user, previous_user=identity, package=package
            )
            return entry

    @route()
    def drop_user(self, identity: str) -> dict[str, Any]:
        """Drop the user entry (and its pages) and announce it."""
        with self.dispatch_lock:
            entry = self.registry.drop_user(identity)
            self.offer_event("drop_user", user=identity)
            return entry

    # ------------------------------------------------------------------
    # Install primitives — operational: the commander orders them, so they need
    # no event back. The source already spent its copy on the login event.
    # ------------------------------------------------------------------

    @route()
    def add_user(self, identity: str, blob: dict[str, Any]) -> dict[str, Any]:
        """Install a moved user's slice from the decoded blob.

        The item arrives whole, so its identity and every field it carried
        survive the move; ``identity`` is the routing key the CALL was
        addressed with and must match the blob's own user.
        """
        user = blob["user"]
        if user != identity:
            raise ValueError(f"add_user: package of {user!r} addressed to {identity!r}")
        with self.dispatch_lock:
            carried = {k: v for k, v in blob["user_entry"].items() if k != "register_item_id"}
            return self.registry.new_user(user, **carried)

    @route()
    def install_package(self, identity: str, package: str) -> dict[str, Any]:
        """Decode a transport package and install it — the descending move."""
        return self.add_user(identity, pickle.loads(base64.b64decode(package)))
