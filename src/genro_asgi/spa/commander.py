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

"""The UserSticky commander: the pool of workers and the routing picture above it.

The commander is the other half of the UserSticky pair — a derivable base,
never an application: the mountable front, ``SpaApplication`` (phase B), OWNS
a commander rather than deriving from it, so the site-facing routes and the
supervisor never share a namespace and a commander role composes freely. It
owns the :class:`~genro_asgi.channel.hub.ChannelHub` its workers connect to,
spawns and supervises them, and keeps the surface picture of where everything
sits.

**The surface registries are plain dicts, deliberately not the Register
machine of the worker** (the validated lesson: keys and locations up here,
contents down there). There are exactly six, in four groups:

- ``worker_roster`` — worker name → the ROW that holds everything that is that
  worker's:
  ``{status, pid, group, spawned_at, process, users, occupancy, caretaker}``.
  ``status`` walks ``nascent`` (spawned, not yet presented) →
  ``active`` (REGISTER seen) → ``draining`` (deliberately retired) → ``dead``;
  ``users`` maps each held user to ``{pending, last_activity_ts, occupancy}``
  (``pending`` is that user's live calls, ``occupancy`` a field the future
  evaluator fills — 2a never computes it); ``occupancy`` is the window of the
  last ``METRICS_WINDOW`` raw reports the probe collected (the commander
  archives, judging belongs to the evaluator); ``caretaker`` is that worker's
  own probe task, ``None`` when it has none. A user's routing group is its
  worker's ``group``, read from the row.
- ``user_worker_map`` — user identity → the name of the worker holding it, or
  ``None`` while a placement for that user is in flight. It is the ONLY
  structure that says WHERE a user is, and both it and the rows mutate through
  the single pair ``assign_user`` / ``remove_user``.
- ``connection_user`` / ``user_connections`` — the middle level of the ownership
  TREE users → connections, held as the child→parent label plus the parent→child
  edge set.
- ``connection_pages`` / ``page_connection`` — the lower level, the same edge
  both ways: which pages each connection opened, and which connection each page
  belongs to. ``page_connection`` is fed exclusively by the lifecycle fold — the
  ``new_page`` and ``drop_page`` events the REPLYs already carry, plus the
  ``drop_user`` cascade and the drops an expiry sweep ascends — so a live page
  costs no traffic of its own.

The four tree structures are aligned BY CONSTRUCTION: nothing outside
``register_connection`` / ``drop_connection`` / ``register_page`` /
``drop_page`` / ``relabel_user`` / ``remove_user`` ever touches an edge, and
each of those updates every side it concerns in one step. Every read is a
lookup — the demolition of a user is linear in that user's own children, never
a scan of foreign entries.

**Nothing above the written edge is stored: it is DERIVED by walking up the
chain.** A page's user is its connection's user, and a page's worker is its
user's worker — so ``worker_of_page(page_id)`` climbs
``page_connection`` → ``connection_user`` → ``user_worker_map`` and answers
``None`` at any missing hop: a page the surface does not know, a user already
swept, a placement still in flight. That is why a move needs nothing up here
beyond ``assign_user``: pages live where their user lives, with no per-page
write to keep in step, so no duplicate exists that could diverge.

**The third tier of the exchange is a routing job, not a reading one.** A
datachange whose target is not on the worker that produced it ascends here as an
EVENT, and ``route_exchange`` resolves its address — a page by walking its
chain, a user through ``user_worker_map``, or a whole set of pages through the
daemon's filter grammar (``'*'``, or ``'field:value'`` matched on the fields the
walk derives). What it resolves is
buffered per destination worker and flushed as ONE ``/datachange_in`` EVENT per
worker, so a broadcast over N pages of one worker costs one send. The change
itself travels TYTX-encoded and is never opened up here: the address is the whole
of what the commander reads, and an address it cannot resolve is dropped with a
debug log — there is no retry queue.

**dbevents fan out on their own pipe, and the origin is excluded.** A
``subscribeTable`` ascending from a worker folds into ``page_subscriptions`` — a
``SubscriptionIndex`` twin of the one the worker keeps for its own pages, which
exists so this surface can reach the subscribers sitting ANYWHERE else. A
``notifyDbEvents`` carries deposits already shaped by the origin worker, which
already served its own subscribers: every page held by the message's ``worker``
is skipped here, and what is left is buffered per destination and flushed as ONE
``/dbevents_in`` EVENT per worker — a distinct pipe from the exchange's, because
a deposit is not a change. A commit on a table nobody subscribed costs no send at
all; a page whose placement is in flight simply misses it.

**The global store's MASTER lives here, and this is its only writer.** The
``store_set``/``store_del`` messages ascend and are applied to
``global_master``, whose capture-all collector is drained and shipped as ONE
``/global/changes`` EVENT to every active worker — the author's own included, so
one push updates every replica the same way. A worker's replica is seeded inside
``member_joined`` itself (``/global/snapshot``), before it can receive any
incremental change. ``global_lock`` is the read-modify-write grant: FIFO, and it
hands the master's content over with the grant so a holder never mounts a stale
copy. The holder's changes reach the master ONLY at its release, which makes the
whole lock all-or-nothing — a holder that dies has its lock released by the
channel EOF and has written nothing.

**Supervision is the legacy ProcessPool's, over the channel.** A worker is
``sys.executable -m genro_asgi.spa.worker_entry`` with its whole configuration
in the ``GENRO_ASGI_WORKER`` env payload, started in its own session so the
whole process group can be signalled. Readiness is the REGISTER frame, death is
the channel EOF: a worker that is gone is ALWAYS swept — deliberately retired
or crashed, it holds nothing any more — and a crashed one is additionally
relaunched under a **fresh name**, a name never being reused, so no late frame
can be mistaken for the newcomer's. A reconcile task is the safety net for the
one death EOF cannot see, the child that dies before ever connecting; it logs
the exit code and respawns at the next tick, with no backoff of its own.

**Liveness is a pull, and it doubles as the occupancy reading.** Every spawned
worker has its OWN caretaker task, born with its REGISTER and cancelled with
its death: an ``/op/occupancy`` CALL every ``probe_interval``, bounded by
``probe_timeout`` — the only CALL of the system that may expire, because it
carries nothing to lose and the silence IS the information. The worker answers
from its own loop, so one exchange proves the loop is alive and hands over the
counters. An expiry is a SIGKILL to the process group: the EOF that follows
enters the ordinary sweep-and-relaunch path. A probe that raises is logged and
the cadence goes on: the blast radius of a failure is the one worker.

**One fold, one drain.** ``fold_events(worker, events)`` applies the events a
REPLY carried, in the order they were delivered — they are the lifecycle the
answered CALL itself caused, so there is nothing to deduplicate and no
watermark to keep. The drain runs in the commander, never in the transport:
``unwrap_reply`` folds the ``events`` of the payload before reading its
``result``/``error``. The owner check is the only guard, and it is the legacy
rule: a late event never re-points a user already assigned elsewhere; only the
explicit ``assign_user`` decision does that.

**The task class runs after the release, on the same consumer.** A REPLY also
carries ``tasks``: the ascending commands the answered CALL produced for pages
of other workers. ``unwrap_reply`` hands each to ``spawn_command`` — one task
per command, nobody awaiting it — so the caller is released without waiting on a
deposit meant for somebody else. ``fold_command`` is that consumer, and it is
the SAME one ``handle_event`` uses for the outbox EVENTs of the out-of-request
producers: one implementation, both drains.

**The front face is ``forward_call(identity, path, kwargs)``.** ``identity`` is the
sticky key the caller provides — the root avatar identity once logged, the
session id while anonymous; the commander never reads a cookie (that is
``SpaApplication``'s job, phase B). It resolves ``user_worker_map`` and, on a miss,
sends the caller to the **reception**: the first active worker of the pool, the
guests' worker. ``guest_occupancy_limit`` is how many users the reception may
hold before ``check_capacity`` widens the pool. ``forward_envelope`` is the one
implementation behind it: it answers with the result AND, for a page-addressed
CALL, the page's pull delivery under ``DELIVERY_KEYS``, carried through
untouched — the commander is the transport of those changes, never their reader.

**Placement happens at login, and the login waits for it.** The worker pushes:
its ``change_connection_user`` event carries the user's whole slice as a
``package`` and the source has already forgotten it — UNLESS that worker is
already the user's home, and then it links the arriving connection to the
resident entry and sends the login with NO ``package`` at all. That packageless
event is the resident-link announcement: nothing travelled, nothing was flagged,
and ``place_logins`` skips it. The skip leans on one invariant: a user a worker
holds ALWAYS has a key in ``user_worker_map`` — ``install_package``'s caller
assigns the map in the same breath, and the login that creates a user on a
worker ships it out inside the same locked mutation — so the fold of a
packageless login never finds an unplaced user to flag. Everything below is the
road of a login that did push. The caller's own
coroutine runs ``place_login``, and presence comes BEFORE occupancy: a user
somebody already holds goes back to its own worker — sticky wins, no
``decide_worker`` at all, and ``add_user`` there JOINS the arriving connection
onto the resident half (that is the CROSS-worker join: the user's home is not
the worker the connection was sitting on). Only a user nobody holds is a free
choice; that one the
fold flags with ``None`` under its key — "this user's placement is in flight" —
and ``decide_worker`` picks the least-loaded active worker for it. Either way
``install_package`` plants the slice, the map is pointed at the destination, the
flag falls and only THEN is the login result released. The room is ready before
the guest is told its number. A ``forward_call`` that finds the flag up parks on
``placement_done`` — the parked coroutines are the queue, there is no structure
— and re-reads the map on every wakeup, so a flag re-raised by a chained login
simply parks it again. No clock bounds any of it: the install CALL waits, and
the only terminator is the destination's death, which fails that CALL. An
install that fails unmaps a user that was UNPLACED: the source spent its copy,
so that user exists nowhere and the surface says so — but a resident keeps its
placement, because the connection that failed to arrive was never its only one.
Every login has a caller coroutine holding it — a login is caused by a CALL and
comes back on that CALL's REPLY — so ``place_login`` is never detached.

**A total restart is a move whose destination is a file.** With ``dump_path``
armed, ``stop`` walks ``user_worker_map`` and orders every user out with the
commanded ``evict_user`` — the same parcel a login pushes, asked for instead of
announced — and writes them all as one pickle. ``start`` reads that file back
before anything can be routed, renames it ``_loaded`` so a restart that dies
mid-restore cannot install it twice, and places each slice exactly like a
login: ``decide_worker``, the map, ``install_package``. Both halves are
best-effort by design — a worker that cannot answer at stop, a package a worker
refuses at start, are logged and skipped — because the alternative to an
incomplete register is no register at all.

**The single role is configuration, not a subclass.** ``local_worker=True``
(with ``workers=0``) makes the commander build ONE worker in this very process
and attach it to its own hub through a :class:`~genro_asgi.channel.local.LocalChannel`:
same REGISTER, same fresh name, same encode/decode on every frame, same fold —
only the wire is a pair of queues instead of a socket. That worker is the
reception (it is the first active one) and it is also every login's
destination: the user is evicted and reinstalled onto the very worker it came
from, because there is ONE road and no shortcut around it. Design §3.5a: if the
protocol works in the single role, going multi changes nothing but the wire.

Every ``forward_call`` writes itself under the user's ``pending`` in the row and
clears it when it returns; nothing reads that data in 2a — the
commander-initiated move does, when it arrives.
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import logging
import os
import pickle
import re
import signal
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from genro_tytx import from_tytx, to_tytx

from ..channel.frame import Frame
from ..channel.hub import ChannelCallError, ChannelHub, ChannelMember
from ..channel.local import LocalChannel
from .global_store import (
    GLOBAL_CHANGES_PATH,
    GLOBAL_GRANT_PATH,
    GLOBAL_SNAPSHOT_PATH,
    CapturingGlobalStore,
    GlobalStoreLock,
)
from .subscription_index import SubscriptionIndex
from .worker import (
    DATACHANGE_IN_PATH,
    DBEVENTS_IN_PATH,
    DELIVERY_KEYS,
    EXCHANGE_OPS,
    LIFECYCLE_OPS,
    OP_PATH_PREFIX,
    POST_OPS,
    STORE_OPS,
    UserStickyWorker,
)

__all__ = [
    "DEFAULT_GROUP",
    "GUEST_OCCUPANCY_LIMIT",
    "METRICS_WINDOW",
    "PROBE_INTERVAL",
    "PROBE_TIMEOUT",
    "UserStickyCommander",
]

#: The single routing group of 2a: the group column exists everywhere, the
#: groups feature does not. PROVISIONAL — it becomes per-group configuration.
DEFAULT_GROUP = "default"

#: How many raw occupancy reports are kept per worker (~5 minutes at one probe
#: every 5s). PROVISIONAL, transcribed from the legacy commander.
METRICS_WINDOW = 60

#: Seconds between two probes of the same worker. PROVISIONAL — it becomes
#: per-group configuration.
PROBE_INTERVAL = 5.0

#: How long a worker may take to answer its occupancy probe before it is
#: declared gone. The probe is the one CALL that may expire: it carries nothing
#: to lose, and the silence IS the information. PROVISIONAL, as above.
PROBE_TIMEOUT = 10.0

#: The routing key of the occupancy probe.
OCCUPANCY_OP_PATH = f"{OP_PATH_PREFIX}occupancy"

#: How many users the reception may hold before the pool is widened. The 2a
#: reading of occupancy is the head count: no evaluator exists yet, and every
#: guest sits on the reception. PROVISIONAL — it becomes per-group configuration.
GUEST_OCCUPANCY_LIMIT = 50

#: The lifecycle op that is a login: the sticky key changes and a placement is due.
LOGIN_OP = "change_connection_user"

#: The spawn entry point of a worker child.
WORKER_ENTRY_MODULE = "genro_asgi.spa.worker_entry"


class UserStickyCommander:
    """Pool owner and routing surface: spawn, supervise, fold.

    ``workers`` is the initial target size; ``scale()`` moves it afterwards and
    the reconcile task heals the gap. Give ``path``/``host`` to place the hub's
    socket, or neither to let it own a private one.
    """

    RECONCILE_INTERVAL = 0.5
    READY_TIMEOUT = 30.0
    STOP_TIMEOUT = 5.0

    def __init__(
        self,
        *,
        workers: int = 1,
        path: str | None = None,
        host: str | None = None,
        port: int = 0,
        group: str = DEFAULT_GROUP,
        worker_class: str | None = None,
        worker_kwargs: dict[str, Any] | None = None,
        executable: str | None = None,
        max_workers: int | None = None,
        guest_occupancy_limit: int = GUEST_OCCUPANCY_LIMIT,
        probe_interval: float = PROBE_INTERVAL,
        probe_timeout: float = PROBE_TIMEOUT,
        local_worker: bool = False,
        dump_path: str | None = None,
    ) -> None:
        """Args:
        workers: how many children to keep alive.
        path: UDS socket path for the hub (mutually exclusive with ``host``).
        host: TCP host for the hub; ``port=0`` lets the OS choose.
        port: TCP port, with ``host``.
        group: the routing group every worker of this commander belongs to.
        worker_class: dotted ``module:Class`` reference passed to the children.
        worker_kwargs: extra constructor kwargs passed to the worker class.
        executable: the interpreter to spawn with (defaults to this one).
        max_workers: ceiling the capacity check never scales past (None = unbounded).
        guest_occupancy_limit: users on the reception above which the pool widens.
        probe_interval: seconds between two probes of the same worker.
        probe_timeout: how long a worker may take to answer its probe.
        local_worker: hold one worker in this process (the single role, §3.5a);
            pair it with ``workers=0`` to spawn no child at all.
        dump_path: file the whole register is dumped to at ``stop`` and read back
            at ``start`` — the move across a total restart (None disarms it).
        """
        self.target = workers
        self.group = group
        self.worker_class = worker_class
        self.worker_kwargs = dict(worker_kwargs or {})
        self.executable = executable or sys.executable
        self.max_workers = max_workers
        self.guest_occupancy_limit = guest_occupancy_limit
        self.probe_interval = probe_interval
        self.probe_timeout = probe_timeout
        self.local_worker = local_worker
        self.dump_path = dump_path
        # The in-process worker of the single role and the wire it sits on;
        # both stay None in the multi role.
        self.worker: UserStickyWorker | None = None
        self.local_channel: LocalChannel | None = None
        self.logger = logging.getLogger(__name__)
        self.hub = ChannelHub(
            path=path,
            host=host,
            port=port,
            on_member_joined=self.member_joined,
            on_channel_lost=self.channel_lost,
            on_event=self.handle_event,
        )
        # The whole surface: one row per worker, one entry per user. ``None`` in
        # the map is the flag "this user's placement is in flight".
        self.worker_roster: dict[str, dict[str, Any]] = {}
        self.user_worker_map: dict[str, str | None] = {}
        # The middle link of the ownership chain: which user each connection is,
        # and the same edge read downward — the two sides move together.
        self.connection_user: dict[str, str] = {}
        self.user_connections: dict[str, set[str]] = {}
        # The lower edge of the tree, both ways: which pages each connection
        # opened, and which connection each page belongs to. Nothing else about
        # a page is written — its user and its worker are derived by walking up.
        self.connection_pages: dict[str, set[str]] = {}
        self.page_connection: dict[str, str] = {}
        # The cross-worker dbevents surface, fed by the ascending subscriptions.
        # No lock: every mutation of it is a sync method on this loop.
        self.page_subscriptions = SubscriptionIndex()
        # The global store: the MASTER lives here and only this object writes it,
        # so its captures are the whole of what the replicas ever see.
        self.global_master = CapturingGlobalStore()
        self.global_lock = GlobalStoreLock()
        # Fired-and-rearmed at the end of every placement: the coroutines parked
        # on it while a flag is up ARE the queue of waiters.
        self.placement_done = asyncio.Event()
        self._reconcile_task: asyncio.Task[None] | None = None
        # Strong refs to the task-class commands in flight: the loop keeps only
        # weak ones, and nobody awaits these.
        self._command_tasks: set[asyncio.Task[None]] = set()
        self._wakeup = asyncio.Event()

    @property
    def address(self) -> str:
        """The address the children connect to."""
        return self.hub.address

    @property
    def active_workers(self) -> list[str]:
        """The names of the workers currently connected, in spawn order."""
        return [
            name for name, entry in self.worker_roster.items() if entry["status"] == "active"
        ]

    @property
    def living_workers(self) -> list[str]:
        """The names of the workers that count toward the target (nascent + active)."""
        return [
            name
            for name, entry in self.worker_roster.items()
            if entry["status"] in ("nascent", "active")
        ]

    @property
    def reception(self) -> str | None:
        """The guests' worker: the FIRST active one, in spawn order.

        Positional, like the legacy reception: no flag and no election, so a
        reception that dies is silently succeeded by the next worker.
        """
        active = self.active_workers
        return active[0] if active else None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Bind the hub, attach the local worker if any, start supervision.

        The in-process worker joins BEFORE the first reconcile, so it is the
        first member of the roster and therefore the reception. The caretakers
        are not started here: each is born with its own worker's REGISTER.

        The dump of the previous run is read back LAST, when there is a pool to
        install it on.
        """
        await self.hub.start()
        if self.local_worker:
            await self.attach_local_worker()
        self._reconcile_task = asyncio.create_task(self.reconcile_loop())
        self._wakeup.set()
        await self.restore_dump()

    async def stop(self) -> None:
        """Deliberate shutdown: retire every worker, close the hub, clean up.

        The caretaker sweep runs LAST, once the hub is stopped. ``channel_lost``
        still fires during the retire and cancels those caretakers itself; what
        no channel loss ever cancels — a nascent child, the local worker, a
        late REGISTER landing mid-stop — is exactly what the final sweep ends,
        and with the hub closed no ``member_joined`` can birth another.

        The register is dumped FIRST, while every worker is still there to be
        asked for its slice: after the retire there is nobody left holding one.
        """
        await self.write_dump()
        if self._reconcile_task is not None:
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass
        self._reconcile_task = None
        self.target = 0
        retired = list(self.living_workers)
        for name in retired:
            self.retire_worker(name)
        if self.worker is not None:
            await self.worker.shutdown()
            self.worker = None
            self.local_channel = None
        await self.wait_workers_end(retired)
        await self.hub.stop()
        for name in list(self.worker_roster):
            self.cancel_caretaker(name)

    async def write_dump(self) -> None:
        """Take every user off its worker and write the whole register to disk.

        A total restart is a move whose destination is a file: the slices leave
        the workers by the ONE road out — the commanded ``evict_user`` — and
        wait in the parcel they always travel in. Every user is asked for by
        identity, so each request lands on the worker that actually holds it.

        Best-effort, like the session snapshot it follows: a user whose worker
        cannot answer is logged and left behind, because a dying pool is exactly
        when this runs and refusing to write the rest would save nothing.

        The surface forgets each user the moment its parcel is in hand — the
        same ``remove_user`` every other departure folds into — so a stopped
        commander holds no placement for what now lives on disk.
        """
        if self.dump_path is None:
            return
        packages: dict[str, str] = {}
        for user in list(self.user_worker_map):
            try:
                result = await self.forward_call(user, f"{OP_PATH_PREFIX}evict_user")
            except Exception as exc:
                self.logger.warning("Dump of %s failed (%s: %s)", user, type(exc).__name__, exc)
            else:
                packages[user] = result["package"]
                self.remove_user(user)
        target = Path(self.dump_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pickle.dumps(packages))
        self.logger.info("Dumped %d users to %s", len(packages), target)

    async def restore_dump(self) -> None:
        """Install the previous run's dump on the new pool, then retire the file.

        The dump is RENAMED to ``<stem>_loaded<suffix>`` — the daemon's own
        anti-double-load rename (siteregister.py:859-870), a stale one removed
        first — and renamed before a single package is installed: a restart that
        dies mid-restore must not find the file again and install everything
        twice. The readiness wait comes BEFORE the rename: a pool that never
        presents itself aborts the restore with the dump still in place, so the
        next start finds it and tries again.

        Each slice is placed like a login: a worker is decided, the map points
        at it, and ``install_package`` rebuilds indexes, collectors, views and
        pendings BY CONSTRUCTION — there is nothing to re-index and no trigger
        to re-hook. The SURFACE is re-hung here, from the package's own record
        (``adopt_slice``): the operational install sends no events, and a
        restarted process folds from nothing. A package the destination refuses
        is logged and dropped: the surface simply never learns that user.
        """
        if self.dump_path is None:
            return
        source = Path(self.dump_path)
        if not source.exists():
            return
        packages: dict[str, str] = pickle.loads(source.read_bytes())
        await self.wait_workers_ready()
        loaded = source.with_name(f"{source.stem}_loaded{source.suffix}")
        loaded.unlink(missing_ok=True)
        source.rename(loaded)
        path = f"{OP_PATH_PREFIX}install_package"
        for user, package in packages.items():
            destination = self.decide_worker()
            self.assign_user(user, destination)
            try:
                payload = await self.hub.call(
                    destination, path, {"identity": user, "kwargs": {"package": package}}
                )
                await self.unwrap_reply(destination, path, payload)
            except Exception as exc:
                self.remove_user(user)
                self.logger.warning(
                    "Restore of %s failed (%s: %s)", user, type(exc).__name__, exc
                )
            else:
                self.adopt_slice(user, destination, package)
                self.logger.info("Restored %s on %s", user, destination)

    def adopt_slice(self, user: str, worker: str, package: str) -> None:
        """Relearn the surface of a restored slice — the fold the install never sends.

        Operational installs shape no events (the surface is the one that
        ordered them), and a restarted process folds from an empty surface: the
        only record of the slice's connections, pages and table subscriptions
        is the package itself — the daemon's ``load()`` rebuilds its own dicts
        from the file the same way (siteregister.py:859-870). ``assign_user``
        has already pointed the map; here the chain below it is re-hung, with
        the same mutators the lifecycle fold uses.
        """
        blob = pickle.loads(base64.b64decode(package))
        for connection_id in blob["connections"]:
            self.register_connection(connection_id, user)
        for page_id, packed in blob["pages"].items():
            self.register_page(page_id, user, worker, packed["connection_id"])
            for table in packed["table_subscriptions"]:
                self.page_subscriptions.subscribe(page_id, table)

    async def wait_workers_ready(
        self, count: int | None = None, timeout: float | None = None
    ) -> None:
        """Block until ``count`` workers have presented themselves (readiness gate)."""
        expected = self.target if count is None else count
        limit = self.READY_TIMEOUT if timeout is None else timeout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + limit
        while len(self.active_workers) < expected:
            if loop.time() >= deadline:
                raise TimeoutError(
                    f"{len(self.active_workers)}/{expected} workers ready within {limit}s"
                )
            await asyncio.sleep(0.02)

    def scale(self, count: int) -> None:
        """Move the target to ``count``; reconcile spawns or retires the difference."""
        self.target = count
        surplus = len(self.living_workers) - count
        if surplus > 0:
            for name in self.living_workers[-surplus:]:
                self.retire_worker(name)
        self._wakeup.set()

    def retire(self, name: str) -> None:
        """Retire one named worker and lower the target so reconcile keeps it out."""
        if name not in self.worker_roster:
            raise KeyError(f"no such worker to retire: {name!r}")
        self.target = max(0, self.target - 1)
        self.retire_worker(name)

    # ------------------------------------------------------------------
    # Supervision — the legacy ProcessPool over the channel
    # ------------------------------------------------------------------

    async def reconcile_loop(self) -> None:
        """Keep the living workers == target; woken early by deaths and scale."""
        while True:
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=self.RECONCILE_INTERVAL)
            except TimeoutError:
                pass
            self._wakeup.clear()
            self.reconcile()

    def reconcile(self) -> None:
        """Cull the children that will never present themselves, spawn the shortfall."""
        now = time.monotonic()
        for name, entry in list(self.worker_roster.items()):
            if entry["status"] != "nascent":
                continue
            process = entry["process"]
            if process is not None and process.poll() is not None:
                self.logger.warning(
                    "Worker %s died before registering (exit code %s)", name, process.poll()
                )
                entry["status"] = "dead"
            elif now - entry["spawned_at"] > self.READY_TIMEOUT:
                self.logger.warning("Worker %s never registered: retiring", name)
                self.retire_worker(name)
        for _ in range(max(0, self.target - len(self.living_workers))):
            self.spawn_worker()

    async def caretaker(self, name: str) -> None:
        """Probe ONE worker on its own cadence, forever — the legacy per-child beat.

        The probe is the commander's liveness reading: it is the one CALL with a
        deadline, because it carries nothing to lose and the silence itself is
        the answer. A worker that does not report in ``probe_timeout`` is killed
        outright — the EOF that follows is the death the sweep already knows how
        to handle. A probe that raises is logged and the cadence goes on: one
        caretaker never takes down another worker's.
        """
        while True:
            await asyncio.sleep(self.probe_interval)
            try:
                await self.probe_worker(name)
            except Exception:
                self.logger.exception("Caretaker of worker %s: probe failed", name)

    def cancel_caretaker(self, name: str) -> None:
        """End the caretaker of one worker; a row without one is left alone."""
        task = self.worker_roster[name]["caretaker"]
        if task is not None:
            task.cancel()
            self.worker_roster[name]["caretaker"] = None

    async def probe_worker(self, name: str) -> None:
        """Ask one worker for its occupancy and archive what comes back."""
        try:
            payload = await self.hub.call(
                name,
                OCCUPANCY_OP_PATH,
                {"identity": None, "kwargs": {}},
                timeout=self.probe_timeout,
            )
            report = await self.unwrap_reply(name, OCCUPANCY_OP_PATH, payload)
        except TimeoutError:
            self.logger.warning("Worker %s did not answer the probe: killing", name)
            self.signal_worker(name, signal.SIGKILL)
        except (ConnectionError, ChannelCallError, LookupError) as exc:
            self.logger.debug("Probe of %s skipped (%s: %s)", name, type(exc).__name__, exc)
        else:
            self.record_occupancy(name, report)

    def next_worker_name(self) -> str:
        """Mint a fresh typed channel name; collision is impossible by construction."""
        return f"W:{uuid.uuid4().hex}"

    def new_roster_row(self, pid: int, process: subprocess.Popen[bytes] | None) -> dict[str, Any]:
        """One roster row: everything that is this worker's, in a single place.

        The row is born ``nascent`` and empty — the users arrive with the fold,
        the occupancy window with the reports, the caretaker with the REGISTER.
        It is never dropped: the roster is the record of who existed.
        """
        return {
            "status": "nascent",
            "pid": pid,
            "group": self.group,
            "spawned_at": time.monotonic(),
            "process": process,
            "users": {},
            "occupancy": deque(maxlen=METRICS_WINDOW),
            "caretaker": None,
        }

    def new_user_row(self) -> dict[str, Any]:
        """One user's half of a roster row: its live calls and its activity.

        ``occupancy`` is the per-user reading the future evaluator fills; 2a
        writes the field and never computes it.
        """
        return {"pending": {}, "last_activity_ts": time.time(), "occupancy": None}

    def spawn_payload(self, name: str) -> dict[str, Any]:
        """The ``GENRO_ASGI_WORKER`` object of one child."""
        payload: dict[str, Any] = {"name": name, "address": self.address}
        if self.worker_class is not None:
            payload["worker_class"] = self.worker_class
        if self.worker_kwargs:
            payload["kwargs"] = self.worker_kwargs
        return payload

    def spawn_worker(self) -> str:
        """Start one child process; it will present itself on the channel."""
        name = self.next_worker_name()
        env = dict(os.environ)
        env["GENRO_ASGI_WORKER"] = json.dumps(self.spawn_payload(name))
        process = subprocess.Popen(
            [self.executable, "-m", WORKER_ENTRY_MODULE], env=env, start_new_session=True
        )
        self.worker_roster[name] = self.new_roster_row(process.pid, process)
        self.logger.info("Spawned worker %s (pid %s)", name, process.pid)
        return name

    def load_worker_class(self) -> type[UserStickyWorker]:
        """The worker class of this pool — the very one a spawned child loads."""
        if self.worker_class is None:
            return UserStickyWorker
        module_path, _, class_name = self.worker_class.partition(":")
        return getattr(importlib.import_module(module_path), class_name)

    async def attach_local_worker(self) -> str:
        """Build the in-process worker and present it on the hub — the single role.

        A spawned child's wiring with the fork taken out: a roster entry with
        ``process=None`` where the OS handle would be, a REGISTER over the
        ``LocalChannel`` and the same receive loop on the hub side. Every frame
        still crosses encode/decode, so this is the whole protocol, not a
        shortcut around it.
        """
        name = self.next_worker_name()
        self.worker_roster[name] = self.new_roster_row(os.getpid(), None)
        self.worker = self.load_worker_class()(name, **self.worker_kwargs)
        self.local_channel = LocalChannel(name)
        self.worker.attach_channel(self.local_channel)
        await self.local_channel.connect()
        await self.hub.attach_local(self.local_channel)
        await self.worker.start()
        self.logger.info("Local worker %s attached in-process", name)
        return name

    def retire_worker(self, name: str) -> None:
        """Deliberately drain one worker: no death signal, no relaunch."""
        entry = self.worker_roster[name]
        entry["status"] = "draining"
        self.signal_worker(name, signal.SIGTERM)

    def signal_worker(self, name: str, sig: int) -> None:
        """Signal the worker's whole process group (idempotent, reaps descendants)."""
        process = self.worker_roster[name]["process"]
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except ProcessLookupError:
            pass

    async def wait_workers_end(self, names: list[str]) -> None:
        """Async-poll the retired children, escalating to SIGKILL at the timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.STOP_TIMEOUT
        while any(self.worker_alive(name) for name in names):
            if loop.time() >= deadline:
                for name in names:
                    if self.worker_alive(name):
                        self.signal_worker(name, signal.SIGKILL)
                break
            await asyncio.sleep(0.05)

    def worker_alive(self, name: str) -> bool:
        """Whether the worker's process is still running."""
        process = self.worker_roster[name]["process"]
        return process is not None and process.poll() is None

    # ------------------------------------------------------------------
    # Channel callbacks
    # ------------------------------------------------------------------

    async def member_joined(self, member: ChannelMember) -> None:
        """REGISTER seen: the worker is ready to be routed to, and to be watched.

        Its caretaker is born here — only for a row with a real process: an
        in-process worker cannot outlive the commander that probes it. Async
        because the newcomer's replica is seeded HERE, inside the registration
        itself, which is the only place where "the snapshot before any
        incremental change" is a fact rather than a hope.
        """
        entry = self.worker_roster.get(member.name)
        if entry is None:
            self.logger.warning("Foreign member on the commander hub: %s", member.name)
            return
        entry["status"] = "active"
        entry["pid"] = member.pid
        await self.bootstrap_replica(member.name)
        if entry["process"] is not None:
            entry["caretaker"] = asyncio.create_task(self.caretaker(member.name))
        self.logger.info("Worker %s active (pid %s)", member.name, member.pid)

    async def channel_lost(self, member: ChannelMember) -> None:
        """The channel EOF ends a worker: its users are swept either way.

        Deliberate or not, a worker that is gone holds nothing any more: the
        users on its row exist nowhere and the surface must say so. What the
        crash alone adds is the escalation (a member that lost the channel but
        still breathes is killed) and the relaunch wakeup — a retired worker is
        not replaced. Either way the caretaker ends with the worker it watched.
        """
        entry = self.worker_roster.get(member.name)
        if entry is None:
            return
        deliberate = entry["status"] == "draining"
        entry["status"] = "dead"
        self.cancel_caretaker(member.name)
        if self.global_lock.held_by(member.name):
            self.global_lock.release()
            self.logger.info(
                "Worker %s is gone holding the global-store lock: released, master untouched",
                member.name,
            )
        if deliberate:
            swept = self.sweep_worker(member.name)
            self.logger.info("Worker %s retired: swept %s users", member.name, len(swept))
            return
        if self.worker_alive(member.name):
            self.logger.warning("Worker %s lost the channel but is alive: killing", member.name)
            self.signal_worker(member.name, signal.SIGKILL)
        swept = self.sweep_worker(member.name)
        self.logger.info("Worker %s died: swept %s users, relaunching", member.name, len(swept))
        self._wakeup.set()

    async def handle_event(self, member: ChannelMember, frame: Frame) -> None:
        """The outbox rail: a command a worker produced outside any CALL.

        The lifecycle never arrives here — it rides the REPLY of the CALL that
        caused it, and the occupancy is answered to a probe. What does arrive is
        the third tier of an out-of-request producer: a datachange whose target
        is not on the worker that produced it, for this surface to resolve. The
        same command born INSIDE a CALL arrives on that CALL's REPLY, and both
        drains hand it to the one consumer.
        """
        await self.fold_command(member.name, frame.data or {})

    async def fold_command(self, worker: str, message: dict[str, Any]) -> None:
        """Run one ascending command, whatever drain delivered it.

        One implementation, both drains: the op family says where the command
        goes, and every ascending message carries its own ``op`` — the outbox
        EVENT and the REPLY task class are the same shape.

        The LIFECYCLE family reaches here from ONE producer, the expiry sweep:
        a drop decided on the worker's own clock has no CALL to ride, so it
        ascends alone and is folded exactly like the same event arriving on a
        REPLY. The login never comes this way — it is caused by a CALL.
        """
        op = message.get("op")
        if op in EXCHANGE_OPS:
            await self.route_exchange(message)
            return
        if op in POST_OPS:
            await self.apply_post(message)
            return
        if op in STORE_OPS:
            await self.apply_store(worker, message)
            return
        if op in LIFECYCLE_OPS:
            self.fold_events(worker, [message])
            return
        self.logger.debug("No consumer for command %r from %s", op, worker)

    # ------------------------------------------------------------------
    # The exchange switch, third tier: resolve, buffer, one send per worker
    # ------------------------------------------------------------------

    async def route_exchange(self, message: dict[str, Any]) -> None:
        """Resolve one ascending message and ship it to the workers it reaches.

        The commander is the router and nothing more: it reads the address off
        the header — ``kind``, ``target``, ``filters`` — and never opens the
        TYTX parcel the message carries. A broadcast fans out into one item per
        matching page, and items sharing a destination worker are batched, so a
        broadcast over N pages of one worker costs ONE send.
        """
        buffer: dict[str, list[dict[str, Any]]] = {}
        for worker, item in self.exchange_destinations(message):
            buffer.setdefault(worker, []).append(item)
        await self.flush_exchange(buffer)

    def exchange_destinations(self, message: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        """Every ``(worker, message)`` pair one ascending message resolves to.

        An address the surface cannot resolve — an unknown page, a user whose
        placement is in flight, a target already swept — is dropped with a debug
        log: a change is a signal and there is no retry queue (the legacy rule,
        verbatim). A ``connection_store`` target is a session id, resolved in
        two hops along the ownership chain — ``connection_user`` then
        ``user_worker_map`` — since a connection lives where its user lives.
        """
        if message["filters"] is not None:
            return [
                (worker, {**message, "target": page_id, "filters": None})
                for page_id, worker in self.matching_pages(message["filters"])
                if worker is not None
            ]
        target = message["target"]
        if message["kind"] == "user_store":
            worker = self.user_worker_map.get(target)
        elif message["kind"] == "connection_store":
            user = self.connection_user.get(target)
            worker = None if user is None else self.user_worker_map.get(user)
        else:
            worker = self.worker_of_page(target)
        if worker is None:
            self.logger.debug(
                "exchange dropped: no routable target %r (%s)", target, message["kind"]
            )
            return []
        return [(worker, message)]

    def matching_pages(self, filters: str) -> list[tuple[str, str | None]]:
        """The ``(page_id, worker)`` pairs a filter addresses: every page, or one
        field's exact value.

        ``'*'`` (or nothing) is every page. Anything else is ONE ``field:value``
        pair, compared against the three fields the walk up the chain derives —
        ``connection`` is the written edge, ``user`` its owner, ``worker`` that
        user's placement: all three links of one chain, so the surface holds no
        second independent field to conjoin. A field it does not carry matches
        nothing.

        The comparison is the daemon's own ``checkpage``
        (gnr/web/daemon/siteregister.py:450-456), transcribed: an empty value
        never matches, a non-string compares by equality, a string is
        ``re.match``\\ ed against the filter — prefix-anchored, as the daemon
        anchors it — and an invalid pattern is no match rather than an error.

        The daemon's multi-pair grammar belongs to ``pages()``, the query over
        the rich worker rows (owner's decision 2026-08-06: that is a phase-B
        fan-out, worker → commander → every worker). It is not emulated here:
        an expression this surface cannot answer is an error, not a silently
        empty broadcast.
        """
        if not filters or filters == "*":
            return [(page_id, self.worker_of_page(page_id)) for page_id in self.page_connection]
        if " AND " in filters:
            raise ValueError(
                f"filter {filters!r}: the page surface answers one field:value pair — "
                "the multi-pair grammar lives in pages()"
            )
        name, _, value = filters.partition(":")
        matched = []
        for page_id, connection in self.page_connection.items():
            user = self.connection_user.get(connection)
            worker = None if user is None else self.user_worker_map.get(user)
            derived = {"worker": worker, "user": user, "connection": connection}
            if self.field_matches(derived.get(name), value):
                matched.append((page_id, worker))
        return matched

    def field_matches(self, value: Any, expression: str) -> bool:
        """The daemon's ``checkpage`` comparison (siteregister.py:450-456).

        The daemon's ``bytes`` branch has no counterpart: the three derived
        fields are strings or ``None``.
        """
        if not value:
            return False
        if not isinstance(value, str):
            return bool(expression == value)
        try:
            return bool(re.match(expression, value))
        except Exception:
            return False

    async def flush_exchange(self, buffer: dict[str, list[dict[str, Any]]]) -> None:
        """Ship the buffer: ONE ``/datachange_in`` EVENT per destination worker."""
        for worker, batch in buffer.items():
            try:
                await self.hub.post(worker, DATACHANGE_IN_PATH, batch)
            except (LookupError, ConnectionError) as exc:
                self.logger.debug("datachange_in missed %s: %s", worker, exc)

    # ------------------------------------------------------------------
    # The dbevents surface: subscriptions fold in, batches fan out to the
    # OTHER workers. Its own pipe, never the exchange one.
    # ------------------------------------------------------------------

    async def apply_post(self, message: dict[str, Any]) -> None:
        """Fold one ascending POST: a subscription, or a commit to fan out."""
        if message["op"] == "subscribeTable":
            self.fold_subscription(message)
            return
        await self.fan_out_dbevents(message)

    def fold_subscription(self, message: dict[str, Any]) -> None:
        """Mirror a worker's local subscription on the cross-worker surface.

        The worker keeps its own index for the pages it holds; this one exists so
        the fan-out can reach the subscribers sitting anywhere else.
        """
        page_id, table = message["page_id"], message["table"]
        if message.get("subscribe", True):
            self.page_subscriptions.subscribe(page_id, table)
        else:
            self.page_subscriptions.unsubscribe(page_id, table)

    async def fan_out_dbevents(self, message: dict[str, Any]) -> None:
        """Deliver a commit's deposits to the subscribers of the OTHER workers.

        Origin exclusion (§2.4, verbatim): the worker that produced the commit
        already served its own pages, so every page it holds is skipped here —
        the ``worker`` stamp on the message is what says which. A page whose
        placement is in flight is skipped too: a dbevent is a signal and there is
        no retry queue. Deposits sharing a destination worker are batched, so a
        commit reaching N pages of one worker costs ONE send.
        """
        origin = message.get("worker")
        buffer: dict[str, list[dict[str, Any]]] = {}
        for deposit in message.get("deposits") or []:
            for page_id in self.page_subscriptions.pages_for(deposit["table"]):
                worker = self.worker_of_page(page_id)
                if worker is None or worker == origin:
                    continue
                buffer.setdefault(worker, []).append({"page_id": page_id, "deposit": deposit})
        await self.flush_dbevents(buffer)

    async def flush_dbevents(self, buffer: dict[str, list[dict[str, Any]]]) -> None:
        """Ship the buffer: ONE ``/dbevents_in`` EVENT per destination worker."""
        for worker, batch in buffer.items():
            try:
                await self.hub.post(worker, DBEVENTS_IN_PATH, batch)
            except (LookupError, ConnectionError) as exc:
                self.logger.debug("dbevents_in missed %s: %s", worker, exc)

    # ------------------------------------------------------------------
    # The global store: the master is here, and it is the only writer. Every
    # replica is a consequence of what this object captured.
    # ------------------------------------------------------------------

    async def apply_store(self, worker: str, message: dict[str, Any]) -> None:
        """Fold one ascending global-store message: a write, or a lock's two halves."""
        op = message["op"]
        if op == "store_lock":
            await self.grant_global_lock(worker, message["request_id"])
        elif op == "store_unlock":
            await self.release_global_lock(worker, message)
        elif op == "store_del":
            self.global_master.delete(message["path"])
            await self.propagate_global()
        else:
            self.global_master.set(message["path"], message["value"])
            await self.propagate_global()

    async def bootstrap_replica(self, worker: str) -> None:
        """Seed a fresh worker's replica with the master, before any change of its own.

        The worker is already ``active`` when the snapshot is captured, so a write
        landing while this ship is in flight is posted AFTER it and applies on
        top: the replica is born aligned and stays so. Nothing between the two
        statements awaits, which is what makes that ordering a fact.
        """
        await self.post_global(worker, GLOBAL_SNAPSHOT_PATH, self.global_master.snapshot())

    async def propagate_global(self) -> None:
        """Ship what the master captured to every replica: ONE EVENT per worker.

        Every active worker, the author's own included — its replica is written
        by this very push like all the others, which is exactly why a lock's
        working copy can simply be thrown away at release.
        """
        changes = self.global_master.drain()
        if not changes:
            return
        encoded = to_tytx(changes, "json")
        for worker in self.active_workers:
            await self.post_global(worker, GLOBAL_CHANGES_PATH, encoded)

    async def post_global(self, worker: str, path: str, data: Any) -> None:
        """One global-store EVENT toward one worker; one already gone is skipped."""
        try:
            await self.hub.post(worker, path, data)
        except (LookupError, ConnectionError) as exc:
            self.logger.debug("%s missed %s: %s", path, worker, exc)

    async def grant_global_lock(self, worker: str, request_id: str) -> None:
        """Park on the FIFO lock, then hand the master itself to the winner.

        The grant CARRIES the store, so a holder never has to ask whether its
        replica was current: what it mounts is the master at grant time. A grant
        that cannot be delivered means the winner's channel has ALREADY ended —
        the EOF that releases a holder fired while this waiter was still parked,
        so no further ``channel_lost`` will ever fire for it. Same death rule,
        evaluated now: release on the spot, master untouched, next waiter served.
        """
        await self.global_lock.acquire(worker, request_id)
        try:
            await self.hub.post(
                worker,
                GLOBAL_GRANT_PATH,
                {"request_id": request_id, "store": self.global_master.snapshot()},
            )
        except (LookupError, ConnectionError) as exc:
            self.logger.info(
                "Global-store grant undeliverable to %s (%s): released, master untouched",
                worker,
                exc,
            )
            self.global_lock.release()

    async def release_global_lock(self, worker: str, message: dict[str, Any]) -> None:
        """Apply a holder's changes to the master, release, propagate to everyone.

        The changes land here and nowhere else, so the protocol is all-or-nothing
        by construction. A release for a grant no longer in force applies NOTHING:
        the holder's channel died while the release was on the wire, and the death
        already gave the lock away. The master is written BEFORE the release, so
        the next waiter's grant carries these changes.
        """
        request_id = message["request_id"]
        if not self.global_lock.holds(request_id):
            self.logger.debug("global unlock of a grant no longer in force from %s", worker)
            return
        self.global_master.apply_changes(from_tytx(message["changes"], "json"))
        self.global_lock.release()
        await self.propagate_global()

    async def unwrap_reply(self, worker: str, path: str, payload: dict[str, Any]) -> Any:
        """The REPLY drain: fold the three sub-envelopes, then read the answer.

        Every ``hub.call`` of this commander goes through here. The SYNCHRONOUS
        class runs first, and a login it folds is placed HERE, in the caller's
        own coroutine — so a login result is released only once its user has a
        room on the destination. The TASK class is then handed one task per
        command: the caller waits on none of it. An error payload becomes the
        exception the caller expects — its tasks are spawned all the same, since
        the worker already drained what they carry and the op outcome gates
        neither them nor the delivery.
        """
        await self.place_logins(worker, payload.get("events") or [])
        for command in payload.get("tasks") or []:
            self.spawn_command(worker, command)
        if "error" in payload:
            # The whole REPLY travels on the exception: an errored page CALL
            # still carried its drain, and the op outcome does not gate the
            # delivery (Phase 2 rule) — losing it here would empty collectors
            # the worker already drained.
            raise ChannelCallError(worker, path, payload["error"], payload=payload)
        return payload.get("result")

    def spawn_command(self, worker: str, message: dict[str, Any]) -> asyncio.Task[None]:
        """Run one task-class command on its own task, holding a strong ref.

        The loop keeps only a weak reference to a task, so the set is what keeps
        the work alive until it ends; nobody awaits it, which is the point of
        the class.
        """
        task = asyncio.create_task(self.fold_command(worker, message))
        self._command_tasks.add(task)
        task.add_done_callback(self._command_tasks.discard)
        return task

    # ------------------------------------------------------------------
    # The fold — one implementation, both drains
    # ------------------------------------------------------------------

    def fold_events(self, worker: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply the worker's events in delivered order and return the logins.

        No dedup and no ordering gate: the envelope is causal and delivered
        once, so every event in it is fresh — the legacy removed its own seq
        counters for the same reason (they rejected legitimate post-move
        events). The owner check inside ``fold_event`` is the only guard.
        """
        logins = []
        for event in events:
            self.fold_event(worker, event)
            if event.get("op") == LOGIN_OP:
                logins.append(event)
        return logins

    def fold_event(self, worker: str, event: dict[str, Any]) -> None:
        """Fold one shaped lifecycle event into the surface registries.

        The worker shapes every event whole, so a missing entity key is a
        broken producer and raises (``KeyError``), never passes silently.
        """
        op = event.get("op")
        if op == "new_user":
            self.register_user(event["user"], worker)
        elif op == "drop_user":
            self.drop_user(event["user"], worker)
        elif op == "new_connection":
            self.register_connection(event["session_id"], event["user"])
        elif op == "drop_connection":
            self.drop_connection(event["session_id"])
        elif op == LOGIN_OP:
            self.relabel_user(event["user"], event.get("previous_user"), event["session_id"])
        elif op == "new_page":
            self.register_page(event["page_id"], event["user"], worker, event["session_id"])
        elif op == "drop_page":
            self.drop_page(event["page_id"], worker)
        elif op in LIFECYCLE_OPS:
            self.logger.debug("fold: op %r has no surface consumer yet", op)
        else:
            self.logger.warning("fold: unknown op %r from %s", op, worker)

    def register_user(self, user: str, worker: str) -> None:
        """Map a user to the worker that announced it — the owner check applies.

        An event arriving late from a worker that no longer holds the user never
        re-points it: only the explicit ``assign_user`` decision does.
        """
        if user in self.user_worker_map and self.user_worker_map[user] != worker:
            self.logger.debug("fold: %s already assigned, ignoring %s's claim", user, worker)
            return
        self.assign_user(user, worker)

    def register_connection(self, session_id: str, user: str) -> None:
        """Map a connection to the user it belongs to — the middle link, folded."""
        self.connection_user[session_id] = user
        self.user_connections.setdefault(user, set()).add(session_id)

    def drop_connection(self, session_id: str) -> None:
        """Forget one connection: its pages announced their own drop before it.

        The cascade climbs on the worker and is announced in that order, so by
        the time this arrives the pages of that connection are already gone.
        The user stays: a sibling connection of it is being served all along.
        """
        owner = self.connection_user.pop(session_id, None)
        if owner is not None:
            self.discard_connection_edge(owner, session_id)
        self.connection_pages.pop(session_id, None)

    def discard_connection_edge(self, user: str, session_id: str) -> None:
        """Take one connection off its user's edge set, dropping the set when empty.

        Called only for an owner just read off ``connection_user``, so the edge
        set exists by the alignment invariant — a missing one is a broken
        surface and raises (``KeyError``), never passes silently.
        """
        siblings = self.user_connections[user]
        siblings.discard(session_id)
        if not siblings:
            del self.user_connections[user]

    def connections_of(self, user: str) -> list[str]:
        """Every connection of a user, sorted — the edge set read downward."""
        return sorted(self.user_connections.get(user, set()))

    def relabel_user(self, user: str, previous_user: str | None, session_id: str) -> None:
        """The login: the CONNECTION changes owner, and no page edge ever moves.

        One edge moves, and one only — the surface transcribes what the worker
        did to its own registers: the connection leaves its guest entry and joins
        the real user's. The pages of that connection follow it without being
        touched, because their user is derived from it and never written. The old
        guest leaves the surface once it has no connection left, and by then it
        owns no page either, BY CONSTRUCTION.

        The worker announcing this has already pushed the slice out of its own
        register, so for a user nobody has ever placed the fold writes ``None``
        (placement in flight) and the destination mapping arrives later, from
        ``place_login`` alone.

        A user already placed somewhere is NOT flagged: it is not in flight, it
        is at home. Its other connections are being served there this whole
        time, and the arriving one will join them — blanking the map would park
        every call to a user that never left.
        """
        former_owner = self.connection_user.get(session_id)
        if former_owner is not None and former_owner != user:
            self.discard_connection_edge(former_owner, session_id)
        self.connection_user[session_id] = user
        self.user_connections.setdefault(user, set()).add(session_id)
        if (
            previous_user is not None
            and previous_user != user
            and not self.connections_of(previous_user)
        ):
            self.remove_user(previous_user)
        if user not in self.user_worker_map:
            self.assign_user(user, None)

    def register_page(self, page_id: str, user: str, worker: str, connection: str) -> None:
        """Hang a page under its connection — the owner check applies.

        The user rule, verbatim: a claim from a worker that no longer holds the
        page never re-points it. Where "holds" is now DERIVED — the announcing
        worker is compared against the walk up the known page's chain — and a page
        only ever changes worker with its user, through ``assign_user``.

        ``user`` is not stored: it is the event's word for who owns
        ``connection``, and a connection this surface never heard of is
        self-healed with it. The announcing worker owns both, in the same REPLY
        cascade, so the middle link cannot be missing for any other reason.
        """
        previous = self.page_connection.get(page_id)
        if previous is not None and self.worker_of_page(page_id) != worker:
            self.logger.debug("fold: page %s already placed, ignoring %s's claim", page_id, worker)
            return
        if previous is not None and previous != connection:
            self.discard_page_edge(previous, page_id)
        if connection not in self.connection_user:
            self.register_connection(connection, user)
        self.page_connection[page_id] = connection
        self.connection_pages.setdefault(connection, set()).add(page_id)

    def discard_page_edge(self, session_id: str, page_id: str) -> None:
        """Take one page off its connection's edge set, dropping the set when empty.

        Called only for a connection just read off ``page_connection``, so the
        edge set exists by the alignment invariant — a missing one is a broken
        surface and raises (``KeyError``), never passes silently.
        """
        siblings = self.connection_pages[session_id]
        siblings.discard(page_id)
        if not siblings:
            del self.connection_pages[session_id]

    def drop_page(self, page_id: str, worker: str) -> None:
        """Unhang a page, unless it has meanwhile been placed somewhere else.

        Its subscriptions go with it: a page that exists nowhere subscribes to
        nothing, and a stale entry would make every commit on that table resolve
        a destination for a page nobody holds.
        """
        if self.worker_of_page(page_id) != worker:
            return
        connection = self.page_connection.pop(page_id)
        self.discard_page_edge(connection, page_id)
        self.page_subscriptions.drop_page(page_id)

    def worker_of_page(self, page_id: str) -> str | None:
        """The worker holding a page, DERIVED: page → connection → user → worker.

        ``None`` at any missing hop, which is the whole of the old semantics — a
        page the surface does not know, a connection or user already swept, a
        placement still in flight — now holding by derivation instead of by a
        written flag somebody has to keep in step.
        """
        connection = self.page_connection.get(page_id)
        if connection is None:
            return None
        user = self.connection_user.get(connection)
        if user is None:
            return None
        return self.user_worker_map.get(user)

    def pages_of_connection(self, session_id: str) -> list[str]:
        """Every page opened by one connection, sorted — the edge set read downward."""
        return sorted(self.connection_pages.get(session_id, set()))

    def drop_user(self, user: str, worker: str) -> None:
        """Unmap a user, unless it has meanwhile been assigned somewhere else."""
        if self.user_worker_map.get(user) != worker:
            return
        self.remove_user(user)

    def assign_user(self, user: str, worker: str | None) -> None:
        """Point a user at a worker — the explicit decision, above the owner check.

        One of the two mutators of the surface: the user's half-row travels with
        it, so a re-pointing keeps the pending calls and the activity it already
        had. A user seen for the first time gets a fresh half-row.

        ``worker=None`` raises the placement flag: the user is in the map and on
        no row at all, which is the truth while its slice is on the wire.

        The user's connections and pages travel with it and NOTHING is written
        for them: they answer the new worker the moment this map entry changes,
        because that is where their answer is derived from.
        """
        previous = self.user_worker_map.get(user)
        carried = None
        if previous is not None and previous != worker:
            carried = self.worker_roster[previous]["users"].pop(user, None)
        if worker is not None:
            users = self.worker_roster[worker]["users"]
            if user not in users:
                users[user] = self.new_user_row() if carried is None else carried
        self.user_worker_map[user] = worker

    def remove_user(self, user: str) -> None:
        """Drop a user from the surface: its half-row and its map entry, together.

        The other mutator. A user whose placement is in flight (``None`` in the
        map) has no half-row anywhere, so only the flag goes. The demolition
        follows the chain downward — every connection of the user, every page of
        each connection, and the connection entries after them: a page without
        its user exists nowhere, and neither does a connection.
        """
        worker = self.user_worker_map.pop(user, None)
        if worker is not None:
            del self.worker_roster[worker]["users"][user]
        for session_id in sorted(self.user_connections.pop(user, set())):
            for page_id in sorted(self.connection_pages.pop(session_id, set())):
                del self.page_connection[page_id]
                self.page_subscriptions.drop_page(page_id)
            del self.connection_user[session_id]

    def sweep_worker(self, worker: str) -> list[str]:
        """Forget every user of a dead worker: what they pointed at is gone."""
        doomed = sorted(self.worker_roster[worker]["users"])
        for user in doomed:
            self.remove_user(user)
        return doomed

    def users_on(self, worker: str) -> set[str]:
        """The users this worker holds, read from its row."""
        return set(self.worker_roster[worker]["users"])

    def record_occupancy(self, worker: str, report: dict[str, Any]) -> None:
        """Archive one raw occupancy reading in the worker's window."""
        window = self.worker_roster[worker]["occupancy"]
        window.append({"ts": time.time(), "report": report})

    # ------------------------------------------------------------------
    # The front face: sticky routing, the reception, the capacity check
    # ------------------------------------------------------------------

    async def forward_call(
        self,
        identity: str,
        path: str,
        kwargs: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Forward the call to the worker holding ``identity`` and return its result.

        ``identity`` is the sticky key the caller owns — the root avatar identity
        once logged, the session id while anonymous. A user whose placement is in
        flight is waited for first, so the pick lands on the worker the surface
        finally points at; the whole call is one entry under that user's
        ``pending``.
        """
        envelope = await self.forward_envelope(identity, path, kwargs, timeout)
        return envelope["result"]

    async def forward_envelope(
        self,
        identity: str,
        path: str,
        kwargs: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Forward the call and return its whole envelope: result plus delivery.

        The one implementation of the forward — ``forward_call`` reads the result
        out of it. The pull delivery a page-addressed CALL brought back travels
        under ``DELIVERY_KEYS``, passed through UNTOUCHED to the outer response:
        the commander does not read the changes, it carries them. A CALL that
        addressed no page brings neither key, so neither appears here. A CALL
        that FAILED still carried its drain: the raised ``ChannelCallError``
        holds the whole REPLY as ``payload``, delivery keys included.
        """
        worker = await self.resolve_worker(identity)
        request_id = self.open_request(worker, identity, path)
        try:
            payload = await self.hub.call(
                worker, path, {"identity": identity, "kwargs": kwargs or {}}, timeout=timeout
            )
            result = await self.unwrap_reply(worker, path, payload)
        finally:
            self.close_request(worker, identity, request_id)
        envelope: dict[str, Any] = {"result": result}
        envelope.update({key: payload[key] for key in DELIVERY_KEYS if key in payload})
        return envelope

    async def resolve_worker(self, identity: str) -> str:
        """The worker to route ``identity`` to, once no placement of it is in flight."""
        await self.await_placement(identity)
        return self.worker_for(identity)

    def worker_for(self, identity: str) -> str:
        """The worker holding ``identity`` — the reception when nobody does.

        A miss is a guest (or a user whose worker died): it goes to the reception,
        which is also the moment to check whether the pool still has room for one.
        A ``None`` is not a miss but the placement flag: nobody may be routed
        while the destination is being decided.
        """
        if identity in self.user_worker_map:
            worker = self.user_worker_map[identity]
            if worker is None:
                raise RuntimeError(f"placement of {identity} is in flight")
            if self.worker_roster[worker]["status"] == "active":
                return worker
        reception = self.reception
        if reception is None:
            raise RuntimeError("no worker available to serve the request")
        self.check_capacity()
        return reception

    def decide_worker(self) -> str:
        """Where an UNPLACED just-logged user belongs: the least-loaded worker.

        Occupancy is the second step of the placement and it only ever sees the
        users nobody holds — ``place_login`` answers the presence question
        before asking this one. Head count is the 2a reading of load — the
        evaluator that measures the real thing is out of scope. The capacity
        check runs AFTER the pick, so a login never lands on the worker its own
        arrival spawned.
        """
        candidates = self.active_workers
        if not candidates:
            raise RuntimeError("no worker available to place a login")
        chosen = min(candidates, key=lambda name: len(self.users_on(name)))
        self.check_capacity()
        return chosen

    def check_capacity(self) -> None:
        """Widen the pool when the reception has no room left for its guests.

        A spawn already in flight is waited for instead of being stacked on, and
        ``max_workers`` is a hard ceiling.
        """
        reception = self.reception
        if reception is None or len(self.users_on(reception)) < self.guest_occupancy_limit:
            return
        if len(self.living_workers) > len(self.active_workers):
            return
        if self.max_workers is not None and self.target >= self.max_workers:
            self.logger.warning("Pool full at max_workers=%s; not scaling", self.max_workers)
            return
        self.scale(self.target + 1)
        self.logger.info("Reception %s is full; scaled to %s", reception, self.target)

    # ------------------------------------------------------------------
    # The live calls, written under the user they belong to
    # ------------------------------------------------------------------

    def open_request(self, worker: str, user: str, path: str) -> str:
        """Write one live call under the user's half-row; returns the id that closes it.

        A guest calling for the first time has no half-row yet — the fold of its
        ``new_user`` has not run — so the call itself opens one on the worker
        that is about to serve it.
        """
        users = self.worker_roster[worker]["users"]
        if user not in users:
            users[user] = self.new_user_row()
        entry = users[user]
        request_id = uuid.uuid4().hex
        entry["pending"][request_id] = {"path": path, "ts": time.time()}
        entry["last_activity_ts"] = time.time()
        return request_id

    def close_request(self, worker: str, user: str, request_id: str) -> None:
        """Clear one live call from the user's half-row (the caller's ``finally``).

        The half-row can be gone by now — the worker died and was swept, or the
        user was placed elsewhere — and then there is nothing left to clear.
        """
        entry = self.worker_roster[worker]["users"].get(user)
        if entry is not None:
            entry["pending"].pop(request_id, None)

    # ------------------------------------------------------------------
    # The placement: the login's room, made ready before the key is handed over
    # ------------------------------------------------------------------

    async def place_logins(self, worker: str, events: list[dict[str, Any]]) -> None:
        """Fold this REPLY's events, then hold the caller until each room is ready.

        The fold hands back the logins it applied and they are placed right
        here, in the caller's own coroutine — the only placement path there is,
        because a login exists only as the effect of a CALL. A login result is
        released once its user has a room.

        A login with NO ``package`` is the resident-link announcement: the
        worker that sent it already hosts the user, so it linked the arriving
        connection and shipped nothing. There is no room to make — the user is
        in the one it never left, and the fold raised no flag for it — so the
        event is complete here and never reaches ``place_login``.
        """
        for event in self.fold_events(worker, events):
            if "package" not in event:
                continue
            await self.place_login(event["user"], event["package"])

    async def place_login(self, user: str, package: str) -> None:
        """Give a just-logged user its room: decide, install, map, drop the flag.

        Presence comes BEFORE occupancy: a user already placed goes back to its
        own worker, whatever the load says — the resident half of it is there,
        and ``add_user`` joins the arriving connection onto it. Only a user
        nobody holds is a free choice, and only then does ``decide_worker`` run.

        An unplaced user is flagged in the map (the fold did that) and its slice
        exists only inside ``package`` — the source spent its copy pushing it.
        So there is nothing to roll back: an install that fails — the destination
        dying is the only way it can — leaves it nowhere, and the map is made to
        say exactly that. A RESIDENT user is not removed by a failed install:
        the connection that failed to arrive was never its only one, and taking
        the placement away would evict everything that never moved.
        """
        path = f"{OP_PATH_PREFIX}install_package"
        resident = self.user_worker_map.get(user)
        try:
            destination = resident if resident is not None else self.decide_worker()
            payload = await self.hub.call(
                destination,
                path,
                {"identity": user, "kwargs": {"package": package}},
            )
            await self.unwrap_reply(destination, path, payload)
        except Exception as exc:
            if resident is None:
                self.remove_user(user)
            self.logger.warning("Placement of %s failed (%s: %s)", user, type(exc).__name__, exc)
            raise
        else:
            self.assign_user(user, destination)
            self.logger.info("Placed %s on %s", user, destination)
        finally:
            self.release_placement()

    def release_placement(self) -> None:
        """Wake every coroutine parked on the flag, then re-arm for the next one."""
        self.placement_done.set()
        self.placement_done.clear()

    async def await_placement(self, identity: str) -> None:
        """Hold a call whose user is being placed until the flag drops.

        The parked coroutines are the queue: a wakeup re-reads the map, so one
        that finds the flag up again (a second login chained onto the first)
        simply parks once more. Nothing bounds the wait but the placement
        itself: the destination either answers or dies, and its death fails the
        install CALL.
        """
        while self.user_worker_map.get(identity, "") is None:
            await self.placement_done.wait()
