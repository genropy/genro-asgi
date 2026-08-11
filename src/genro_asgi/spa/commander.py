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
contents down there). There are exactly eight, in five groups:

- ``worker_roster`` — worker name → the ROW that holds everything that is that
  worker's: ``{status, pid, group, spawned_at, died_at, death, process, users,
  occupancy, caretaker}``.
  ``status`` walks ``nascent`` (spawned, not yet presented) →
  ``active`` (REGISTER seen) → ``draining`` (deliberately retired) → ``dead``
  — except a nascent one, which jumps straight to ``dead`` when culled or
  retired (no channel means no drain to complete); ``died_at``/``death``
  (``retired``/``crash``/``stillborn``) are the tombstone stamps
  ``bury_workers`` reads;
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
- ``forward_counters`` / ``user_consumption`` — the forward LEDGER, fed by
  ``forward_envelope``'s clock: per-worker cumulative counters
  (``{requests, errors, seconds}``, dropped only by the burial), and per-user
  cumulative consumption plus its recent-window bucket ring (dropped with the
  user by ``forget_users``).

The four tree structures are aligned BY CONSTRUCTION: nothing outside
``register_connection`` / ``drop_connection`` / ``register_page`` /
``drop_page`` / ``relabel_user`` / ``remove_user`` ever touches an edge, and
each of those updates every side it concerns in one step. Every read is a
lookup — the demolition of a user is linear in that user's own children, never
a scan of foreign entries.

**Nothing above the written edge is stored: it is DERIVED by walking up the
chain.** A page's user is its connection's user, and a page's worker is its
user's worker — so ``page_worker(page_id)`` climbs
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
guests' worker. ``reception_threshold`` is the saturation the reception may reach
before ``check_capacity`` widens the pool. ``forward_envelope`` is the one
implementation behind it: it answers with the result AND, for a page-addressed
CALL, the page's pull delivery under ``DELIVERY_KEYS``, carried through
untouched — the commander is the transport of those changes, never their reader.

**Placement happens at login, and the login waits for it.** The worker pushes:
its ``change_connection_user`` event carries the user's whole slice as a
``encoded`` and the source has already forgotten it — UNLESS that worker is
already the user's home, and then it links the arriving connection to the
resident entry and sends the login with NO ``encoded`` at all. That packageless
event is the resident-link announcement: nothing travelled, nothing was flagged,
and ``place_logins`` skips it. The skip leans on one invariant: a user a worker
holds ALWAYS has a key in ``user_worker_map`` — ``add_user``'s caller
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
``add_user`` plants the slice, the map is pointed at the destination, the
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
login: ``decide_worker``, the map, ``add_user``. Both halves are
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
clears it when it returns. ``move_user`` is what reads it: the commander-initiated
move waits for that half-row to empty before it takes the user anywhere.

**A move is a login the commander asked for.** ``move_user`` raises a barrier
under the user's key — every forward of it parks there, before the pick, so
nothing is routed at a worker the slice is leaving — waits out the user's live
calls within ``move_quiesce_timeout``, then takes the parcel with the same
commanded ``evict_user`` the dump uses and plants it with the same
``add_user`` a login does. The map moves LAST: until the install is
confirmed the user is served from its source, and a budget that expires or a
source that cannot answer simply leaves it there. What has no way back is the
evict: the source strips itself as it answers, so from there on the commander
holds the only copy and keeps offering it rooms — the destination dying sends it
to another worker, the source included — and only an empty pool loses it, with
an explicit error.

**The pool's own beat rides the probe return.** Every archived occupancy report
is fresh knowledge, so ``pool_beat`` runs right behind it and dispatches ONE
pass: ``rebalance_excess`` non-empty — somebody is over its own threshold — sends
a rebalance, and nothing else sends a compaction. Excess before slack, one flag
per force, and the pass is detached: a caretaker never waits on what it started.
The compaction reads the capacity ledger — ``C`` what the pool may take (the
reception up to its threshold, a whole gate each for the others), ``O`` what it
holds in ``worker_load`` — and while ``C - O`` stays over ``compaction_margin``, and
the pool is wider than ``min_workers``, it drains the least loaded NON-reception
worker with ``move_user`` and retires it. A drain that does not empty ends the
pass and retires nothing: a worker still holding state is never retired.

The rebalance works in SATURATION instead: what it relieves is the binding
resource, so a worker one component over its target sheds even while its load
reads low. The whole excess is summed once and one target has to absorb it —
non-reception, not hot, and still under ``1.0 - rebalance_margin`` with the excess
on board — and with nobody able to, the pass widens the pool and ends. The users
that go are the source's saturation apportioned over recent service seconds:
heaviest first onto an empty target, lightest first onto a loaded one and only
above ``rebalance_min_share``, until the budget is covered. A rebalance never
retires anything.
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
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from genro_tytx import from_tytx, to_tytx

from ..channel.frame import Frame
from ..channel.hub import ChannelCallError, ChannelHub, ChannelMember
from ..channel.local import LocalChannel
from .evaluator import OccupancyEvaluator
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
    "COMPACTION_MARGIN",
    "CONSUMPTION_BUCKETS",
    "CONSUMPTION_BUCKET_SECONDS",
    "DEFAULT_GROUP",
    "MAX_PENDING_CYCLES",
    "METRICS_WINDOW",
    "MOVE_QUIESCE_TIMEOUT",
    "PROBE_INTERVAL",
    "PROBE_TIMEOUT",
    "REBALANCE_MARGIN",
    "REBALANCE_MIN_SHARE",
    "RECEPTION_THRESHOLD",
    "TOMBSTONE_SECONDS",
    "UserStickyCommander",
]

#: The single routing group of 2a: the group column exists everywhere, the
#: groups feature does not. PROVISIONAL — it becomes per-group configuration.
DEFAULT_GROUP = "default"

#: How many raw occupancy reports are kept per worker (~5 minutes at one probe
#: every 5s). PROVISIONAL, transcribed from the legacy commander.
METRICS_WINDOW = 60

#: The per-user consumption window: a ring of ``CONSUMPTION_BUCKETS`` slots of
#: ``CONSUMPTION_BUCKET_SECONDS`` each — 6 buckets of 5s = a ~30s window, the
#: mirror of the evaluator's smoothing window. ``user_recent_seconds`` sums the
#: buckets still inside it. PROVISIONAL, transcribed from the legacy commander.
CONSUMPTION_BUCKET_SECONDS = 5.0
CONSUMPTION_BUCKETS = 6

#: Seconds between two probes of the same worker. PROVISIONAL — it becomes
#: per-group configuration.
PROBE_INTERVAL = 5.0

#: How long a worker may take to answer its occupancy probe before it is
#: declared gone. The probe is the one CALL that may expire: it carries nothing
#: to lose, and the silence IS the information. PROVISIONAL, as above.
PROBE_TIMEOUT = 10.0

#: The caretaker's second eye (issue #9): how many probe cycles a worker may
#: sit on an unanswered ``add_user`` handover before it is declared stuck and
#: killed — probes it keeps answering notwithstanding. The kill makes the
#: handover's outcome certain (EOF), so the custody salvage can re-home the
#: user without ever risking a slice alive on two workers.
MAX_PENDING_CYCLES = 3

#: How long a dead worker's roster row — and its forward counters — outlives
#: it before ``reconcile`` buries both, logging the obituary. Long enough for
#: every late reference to settle and for a warm autopsy; the log line is the
#: durable record. PROVISIONAL — it becomes per-group configuration.
TOMBSTONE_SECONDS = 3600.0

#: The routing key of the occupancy probe.
OCCUPANCY_OP_PATH = f"{OP_PATH_PREFIX}occupancy"

#: The routing key of the monitor's register fan-out.
MONITOR_STATE_OP_PATH = f"{OP_PATH_PREFIX}monitor_state"

#: The saturation the reception is judged at: under it the reception keeps the
#: logins it receives, over it it passes them on (and a pool of one widens).
#: Lower than the admission gate on purpose — the reception carries the guests
#: too. PROVISIONAL — it becomes per-group configuration.
RECEPTION_THRESHOLD = 0.5

#: How much free capacity — in whole admitting workers — the pool keeps beyond
#: what it holds before the compaction stops folding workers away. The unit is a
#: worker's gate (1.0 in ratio space), so 1.5 means "a worker and a half of
#: room": high enough that a compaction never hands its survivors a pool that
#: the next login re-widens. PROVISIONAL — it becomes per-group configuration.
COMPACTION_MARGIN = 1.5

#: How far under the gate a rebalance fills its target: the absorber must still
#: sit at ``1.0 - REBALANCE_MARGIN`` once it has taken the whole excess. The
#: anti-ping-pong margin — a target filled right up to the gate would be the next
#: beat's hot worker. PROVISIONAL — it becomes per-group configuration.
REBALANCE_MARGIN = 0.1

#: The smallest share of its worker's saturation a user must carry to be worth
#: shedding onto a LOADED target: under it the move buys nothing and costs a
#: whole slice on the wire. PROVISIONAL — it becomes per-group configuration.
REBALANCE_MIN_SHARE = 0.02

#: How long a commander-initiated move waits for the moving user's live calls to
#: drain before giving up on it. The move is held, not the calls: they were
#: accepted by the source and they finish there.
MOVE_QUIESCE_TIMEOUT = 10.0

#: How often the quiesce wait re-reads the user's pending calls. Nothing signals
#: an emptied half-row — ``close_request`` is a plain dict pop — so the wait polls.
MOVE_QUIESCE_POLL = 0.05

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
        probe_interval: float = PROBE_INTERVAL,
        probe_timeout: float = PROBE_TIMEOUT,
        max_pending_cycles: int = MAX_PENDING_CYCLES,
        local_worker: bool = False,
        dump_path: str | None = None,
        memory_limit_mb: int | None = None,
        admission_threshold: float = 0.8,
        component_targets: dict[str, float] | None = None,
        reception_threshold: float = RECEPTION_THRESHOLD,
        move_quiesce_timeout: float = MOVE_QUIESCE_TIMEOUT,
        compaction_margin: float = COMPACTION_MARGIN,
        min_workers: int = 1,
        rebalance_margin: float = REBALANCE_MARGIN,
        rebalance_min_share: float = REBALANCE_MIN_SHARE,
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
        probe_interval: seconds between two probes of the same worker.
        probe_timeout: how long a worker may take to answer its probe.
        max_pending_cycles: probe cycles a worker may sit on an unanswered
            ``add_user`` handover before the caretaker kills it (issue #9).
        local_worker: hold one worker in this process (the single role, §3.5a);
            pair it with ``workers=0`` to spawn no child at all.
        dump_path: file the whole register is dumped to at ``stop`` and read back
            at ``start`` — the move across a total restart (None disarms it).
        memory_limit_mb: the per-worker memory budget the evaluator's memory
            component is measured against (None = no memory component at all).
        admission_threshold: the uniform fraction of every resource a worker may
            hold before it stops admitting — the denominator of the ratio space.
        component_targets: per-component overrides of that threshold (keys in
            ``COMPONENT_NAMES``, values in (0, 1]); an unknown key is a ValueError.
        reception_threshold: the saturation over which the reception stops keeping
            the logins it receives — and, in a pool of one, widens the pool.
        move_quiesce_timeout: how long a move waits for the user's live calls to
            drain before it aborts and leaves the user on its source.
        compaction_margin: the free capacity, in whole admitting workers, the pool
            keeps above what it holds — the compaction folds a worker away only
            while the headroom stays over it.
        min_workers: the floor the compaction never goes under. Only compaction
            reads it: the scale-up has its own ceiling and ``workers`` is just
            the boot target.
        rebalance_margin: how far under the gate a rebalance leaves its target
            once it has absorbed the whole excess — the anti-ping-pong margin.
        rebalance_min_share: the smallest share of its worker's saturation a user
            must carry to be shed onto a LOADED target.
        """
        self.target = workers
        self.group = group
        self.worker_class = worker_class
        self.worker_kwargs = dict(worker_kwargs or {})
        self.executable = executable or sys.executable
        self.max_workers = max_workers
        self.reception_threshold = reception_threshold
        self.probe_interval = probe_interval
        self.probe_timeout = probe_timeout
        self.max_pending_cycles = max_pending_cycles
        self.local_worker = local_worker
        self.dump_path = dump_path
        self.memory_limit_mb = int(memory_limit_mb) if memory_limit_mb is not None else None
        self.move_quiesce_timeout = move_quiesce_timeout
        self.compaction_margin = compaction_margin
        self.min_workers = min_workers
        self.rebalance_margin = rebalance_margin
        self.rebalance_min_share = rebalance_min_share
        # The judge of the occupancy windows this commander archives.
        self.evaluator = OccupancyEvaluator(
            self,
            admission_threshold=admission_threshold,
            component_targets=component_targets,
        )
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
        # What the forwards cost, read two ways: cumulative per worker, and per
        # user both cumulative and over the recent-consumption ring.
        self.forward_counters: dict[str, dict[str, Any]] = {}
        self.user_consumption: dict[str, dict[str, Any]] = {}
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
        # The users a commander-initiated move is carrying right now, each with
        # the barrier every forward of that user parks on until it lands.
        self.moving: dict[str, asyncio.Event] = {}
        # One handover at most is in flight toward a worker (users arrive
        # minutes apart): worker -> when its unanswered add_user CALL left.
        # Written and cleared by hand_user_to, read by the caretaker (#9).
        self.pending_users: dict[str, float] = {}
        # The beat's two forces, one flag each: a pass in flight is never doubled
        # (one pool, one pass), and the task set is what keeps it alive.
        self.compacting = False
        self.rebalancing = False
        self._pool_tasks: set[asyncio.Task[None]] = set()
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
                packages[user] = result["encoded"]
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
        at it, and ``add_user`` rebuilds indexes, collectors, views and
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
        for user, encoded in packages.items():
            destination = self.decide_worker()
            self.assign_user(user, destination)
            try:
                await self.hand_user_to(destination, user, encoded)
            except Exception as exc:
                self.remove_user(user)
                self.logger.warning(
                    "Restore of %s failed (%s: %s)", user, type(exc).__name__, exc
                )
            else:
                self.adopt_slice(user, destination, encoded)
                self.logger.info("Restored %s on %s", user, destination)

    def adopt_slice(self, user: str, worker: str, encoded: str) -> None:
        """Relearn the surface of a restored slice — the fold the install never sends.

        Operational installs shape no events (the surface is the one that
        ordered them), and a restarted process folds from an empty surface: the
        only record of the slice's connections, pages and table subscriptions
        is the package itself — the daemon's ``load()`` rebuilds its own dicts
        from the file the same way (siteregister.py:859-870). ``assign_user``
        has already pointed the map; here the chain below it is re-hung, with
        the same mutators the lifecycle fold uses.
        """
        blob = pickle.loads(base64.b64decode(encoded))
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
        """Retire one named worker and lower the target so reconcile keeps it out.

        Only a living worker (``nascent`` or ``active``) is retirable: a
        draining one is already leaving, and a dead one is a tombstone —
        flipping it back to ``draining`` would make it unburiable (its
        ``channel_lost`` already fired) and shrink the target for a corpse.
        """
        entry = self.worker_roster.get(name)
        if entry is None:
            raise KeyError(f"no such worker to retire: {name!r}")
        if entry["status"] not in ("nascent", "active"):
            raise ValueError(f"worker {name!r} is {entry['status']}: not retirable")
        self.target = max(0, self.target - 1)
        self.retire_worker(name)

    # ------------------------------------------------------------------
    # Supervision — the legacy ProcessPool over the channel
    # ------------------------------------------------------------------

    async def reconcile_loop(self) -> None:
        """Keep the living workers == target; woken early by deaths and scale.

        The parked wait uses ``asyncio.timeout``, not ``wait_for``: on 3.11 a
        ``cancel()`` landing while ``wait_for`` waits can be swallowed by its
        cancellation race, leaving the task uncancellable and ``stop()``
        parked on it forever (3.12 rebuilt ``wait_for`` on this very block).
        """
        while True:
            try:
                async with asyncio.timeout(self.RECONCILE_INTERVAL):
                    await self._wakeup.wait()
            except TimeoutError:
                pass
            self._wakeup.clear()
            self.reconcile()

    def reconcile(self) -> None:
        """Cull the stillborn, bury the long-dead, spawn the shortfall."""
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
                entry["died_at"] = now
                entry["death"] = "stillborn"
            elif now - entry["spawned_at"] > self.READY_TIMEOUT:
                self.logger.warning("Worker %s never registered: killing", name)
                self.retire_worker(name)  # nascent: the stillborn exit
        self.bury_workers(now)
        for _ in range(max(0, self.target - len(self.living_workers))):
            self.spawn_worker()

    def bury_workers(self, now: float) -> None:
        """Drop the rows (and counters) of workers dead past ``TOMBSTONE_SECONDS``.

        The tombstone has served by then — every late reference has settled —
        so the record leaves memory through this one exit, and the obituary
        line is its durable trace in the log.
        """
        for name, entry in list(self.worker_roster.items()):
            if entry["status"] != "dead" or now - entry["died_at"] <= TOMBSTONE_SECONDS:
                continue
            counters = self.forward_counters.pop(name, None) or {}
            self.logger.info(
                "Worker %s buried: pid=%s group=%s lifetime=%.0fs death=%s "
                "requests=%s errors=%s seconds=%.1f",
                name,
                entry["pid"],
                entry["group"],
                entry["died_at"] - entry["spawned_at"],
                entry["death"],
                counters.get("requests", 0),
                counters.get("errors", 0),
                counters.get("seconds", 0.0),
            )
            del self.worker_roster[name]

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
        """Ask one worker for its occupancy, archive it, and let the beat read it.

        The archived report is fresher knowledge about the pool than anything the
        commander had a moment ago, so the beat runs right behind it: the probe
        return IS the pool's heartbeat (the legacy beat rode the push envelope,
        which the pull probe replaced — declared divergence).

        A good answer is not the whole verdict: the second eye (issue #9) then
        checks ``pending_users`` — a worker that keeps answering probes while
        sitting on an ``add_user`` handover beyond ``max_pending_cycles`` probe
        cycles is stuck where the probe deliberately cannot look (the probe
        avoids the worker's write lock), and is killed like a mute one. The EOF
        makes the handover's outcome certain, so the custody salvage re-homes
        the user.
        """
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
            started = self.pending_users.get(name)
            if started is not None:
                waited = time.time() - started
                if waited > self.max_pending_cycles * self.probe_interval:
                    self.logger.warning(
                        "Worker %s answers probes but sat on a user handover for %.1fs: killing",
                        name,
                        waited,
                    )
                    self.signal_worker(name, signal.SIGKILL)
                    return
            self.record_occupancy(name, report)
            self.pool_beat()

    def next_worker_name(self) -> str:
        """Mint a fresh typed channel name; collision is impossible by construction."""
        return f"W:{uuid.uuid4().hex}"

    def new_roster_row(self, pid: int, process: subprocess.Popen[bytes] | None) -> dict[str, Any]:
        """One roster row: everything that is this worker's, in a single place.

        The row is born ``nascent`` and empty — the users arrive with the fold,
        the occupancy window with the reports, the caretaker with the REGISTER.
        It outlives its worker as the tombstone (late frames and probes still
        resolve the name; ``dead`` stays distinct from never-existed) until
        ``bury_workers`` drops it, ``TOMBSTONE_SECONDS`` after the death.
        """
        return {
            "status": "nascent",
            "pid": pid,
            "group": self.group,
            "spawned_at": time.monotonic(),
            "died_at": None,
            "death": None,
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
        """Deliberately drain one worker: no death signal, no relaunch.

        A nascent one cannot drain: it never REGISTERed, so no ``channel_lost``
        will ever complete the retirement — it takes the stillborn exit
        instead, killed outright (it holds nothing to drain) and stamped dead
        here, whether the retirement came from ``retire``, ``scale`` or the
        READY_TIMEOUT cull.
        """
        entry = self.worker_roster[name]
        if entry["status"] == "nascent":
            self.signal_worker(name, signal.SIGKILL)
            entry["status"] = "dead"
            entry["died_at"] = time.monotonic()
            entry["death"] = "stillborn"
            return
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
        entry["died_at"] = time.monotonic()
        entry["death"] = "retired" if deliberate else "crash"
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

        An ADDRESSED message whose user is being carried waits for the move to
        land, exactly like a call does: past the barrier the map points at the
        destination, so the evict→switch window turns into a delayed correct
        delivery instead of a drop. A filtered broadcast never holds — the
        fan-out is best-effort by design, and a whole beat cannot park on one
        user's move. Every EVENT already runs on its own task, so a held message
        parks nobody else.
        """
        addressed = self.addressed_user(message)
        if addressed is not None:
            await self.await_move(addressed)
        buffer: dict[str, list[dict[str, Any]]] = {}
        for worker, item in self.exchange_destinations(message):
            buffer.setdefault(worker, []).append(item)
        await self.flush_exchange(buffer)

    def addressed_user(self, message: dict[str, Any]) -> str | None:
        """The user ONE ascending exchange message is addressed to, if any.

        ``None`` for a filtered broadcast (it addresses a set, not a user) and
        for an address no hop of the chain resolves — there is nothing to wait
        for either way. The three addressed kinds all reach a user: the user
        store IS the user, a connection through ``connection_user``, a page
        through ``page_connection`` first.
        """
        if message["filters"] is not None:
            return None
        target = message["target"]
        if message["kind"] == "user_store":
            return str(target)
        connection = (
            target if message["kind"] == "connection_store" else self.page_connection.get(target)
        )
        return None if connection is None else self.connection_user.get(connection)

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
            worker = self.page_worker(target)
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
            return [(page_id, self.page_worker(page_id)) for page_id in self.page_connection]
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
                worker = self.page_worker(page_id)
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
        task.add_done_callback(self.log_task_error)
        return task

    def log_task_error(self, task: asyncio.Task[None]) -> None:
        """Leave a line behind when a detached task dies of an exception.

        Nobody awaits a task-class command or a pool pass, so without this the
        exception is retrieved by nobody and the failure is silent. A cancelled
        task is the ordinary shutdown path and says nothing.
        """
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            self.logger.error("Detached task %s failed: %r", task.get_name(), error)

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
        if previous is not None and self.page_worker(page_id) != worker:
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
        if self.page_worker(page_id) != worker:
            return
        connection = self.page_connection.pop(page_id)
        self.discard_page_edge(connection, page_id)
        self.page_subscriptions.drop_page(page_id)

    def page_worker(self, page_id: str) -> str | None:
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
        self.forget_users([user])
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

    def count_forward(self, worker: str, seconds: float, error: bool = False) -> None:
        """Fold one forward into the worker's cumulative counters.

        ``requests`` counts the forwards that completed (an error REPLY is a
        completed forward: the worker answered), ``errors`` the TRANSPORT
        failures — the CALL itself raised, counted here and re-raised — and
        ``seconds`` accumulates the wall time of every forward either way.
        """
        counters = self.forward_counters.setdefault(
            worker, {"requests": 0, "errors": 0, "seconds": 0.0}
        )
        if error:
            counters["errors"] += 1
        else:
            counters["requests"] += 1
        counters["seconds"] += seconds

    def count_user_consumption(self, user: str, seconds: float, now: float | None = None) -> None:
        """Fold one forward's cost into the user's consumption: cumulative + windowed.

        The cumulative ``{requests, seconds}`` is what the population view reads.
        Alongside it, ``buckets`` is the ring the rebalance reads for RECENT load:
        the epoch is ``int(now // CONSUMPTION_BUCKET_SECONDS)`` and the slot
        ``epoch % CONSUMPTION_BUCKETS``; a slot holding a different epoch is stale,
        so it is reset before this forward lands.
        """
        now = time.time() if now is None else now
        entry = self.user_consumption.setdefault(user, self.new_consumption_entry())
        entry["requests"] += 1
        entry["seconds"] += seconds
        epoch = int(now // CONSUMPTION_BUCKET_SECONDS)
        slot = entry["buckets"][epoch % CONSUMPTION_BUCKETS]
        if slot["epoch"] != epoch:
            slot["epoch"] = epoch
            slot["requests"] = 0
            slot["seconds"] = 0.0
        slot["requests"] += 1
        slot["seconds"] += seconds

    def new_consumption_entry(self) -> dict[str, Any]:
        """A fresh consumption entry: cumulative counters plus an empty bucket ring.

        The ring is a FIXED list of ``CONSUMPTION_BUCKETS`` slots; ``epoch = -1``
        marks a slot never written (older than any real epoch, so the window
        ignores it). The slots are filled in place and the list is never resized.
        """
        return {
            "requests": 0,
            "seconds": 0.0,
            "buckets": [
                {"epoch": -1, "requests": 0, "seconds": 0.0} for _ in range(CONSUMPTION_BUCKETS)
            ],
        }

    def user_recent_seconds(self, user: str, now: float | None = None) -> float:
        """The user's service time over the current consumption window.

        The sum of ``seconds`` across the buckets whose epoch is within the last
        ``CONSUMPTION_BUCKETS`` epochs (stale ones excluded). An unknown user, or
        one with no bucket in the window, reads 0.0.
        """
        entry = self.user_consumption.get(user)
        if entry is None:
            return 0.0
        now = time.time() if now is None else now
        epoch = int(now // CONSUMPTION_BUCKET_SECONDS)
        oldest = epoch - CONSUMPTION_BUCKETS + 1
        return sum(bucket["seconds"] for bucket in entry["buckets"] if bucket["epoch"] >= oldest)

    def forget_users(self, users: list[str] | set[str]) -> None:
        """Drop the consumption entries of users that left the surface."""
        for user in users:
            self.user_consumption.pop(user, None)

    def record_occupancy(self, worker: str, report: dict[str, Any]) -> None:
        """Archive one raw occupancy reading in the worker's window.

        Each row is ``{ts, report, forward}``: the arrival time, the worker's raw
        readings, and a snapshot of its cumulative forward counters at that
        moment. ``forward`` is copied (the live counters keep moving), ``report``
        is stored as handed — every report arrives deserialized off the wire, so
        nobody else holds it; copy it here if one is ever built locally.
        Interpreting the window is the evaluator's job, not archived here.
        """
        window = self.worker_roster[worker]["occupancy"]
        counters = self.forward_counters.get(worker) or {
            "requests": 0,
            "errors": 0,
            "seconds": 0.0,
        }
        window.append({"ts": time.time(), "report": report, "forward": dict(counters)})

    def worker_window(self, worker: str) -> deque[dict[str, Any]] | None:
        """The archived occupancy window of one worker, None when it is unknown.

        A worker the roster holds but that has answered no probe yet reads as an
        empty deque — it exists, it has said nothing.
        """
        return self.worker_roster.get(worker, {}).get("occupancy")

    def metrics_view(self) -> dict[str, dict[str, Any]]:
        """The evaluator's read of every active worker, scaled for the monitor.

        Occupancy is the evaluator's SATURATION scaled by 100: it lives in the
        ratio space, so 100 means "at the admission target", not "at the
        hardware ceiling", and a worker past its target reads over 100. The
        history is the per-row saturation, on that same axis — the bar and the
        histogram behind it are read against one scale. Components stay raw
        fractions of their resource (what the sensor saw, not what it is judged
        against): they are the reading, not the verdict. The rates keep their
        own units and ``forward`` carries the cumulative counters as they stand.
        Every number here is the evaluator's: nothing is judged.
        """
        view: dict[str, dict[str, Any]] = {}
        for name in self.active_workers:
            components = self.evaluator.worker_components(name)
            view[name] = {
                "occupancy": round(self.evaluator.worker_saturation(name) * 100),
                "components": {key: round(value * 100) for key, value in components.items()},
                "history": [round(value * 100) for value in self.evaluator.worker_history(name)],
                "rates": self.evaluator.rates_of(name),
                # a copy, like the archived snapshot: the view is the consumer's
                # to annotate, the ledger is not
                "forward": dict(
                    self.forward_counters.get(name)
                    or {"requests": 0, "errors": 0, "seconds": 0.0}
                ),
            }
        return view

    async def fetch_monitor_state(self, worker: str) -> dict[str, Any] | None:
        """One worker's monitor rows, None if it does not answer.

        The fan-out's per-worker leg, deadlined like the probe: silence, a
        refusal or a garbled answer all read the same from here, and become an
        error row upstream. One worker gone must not take the whole view down.
        """
        try:
            payload = await self.hub.call(
                worker,
                MONITOR_STATE_OP_PATH,
                {"identity": None, "kwargs": {}},
                timeout=self.probe_timeout,
            )
            return await self.unwrap_reply(worker, MONITOR_STATE_OP_PATH, payload)
        except Exception as exc:
            self.logger.debug("Monitor state of %s unreachable (%s)", worker, exc)
            return None

    async def population(self) -> dict[str, Any]:
        """Every active worker's registers, with this commander's consumption fused.

        A concurrent ``monitor_state`` fan-out over the channel: the workers
        have no HTTP of their own, so the CALL carries what the legacy monitor
        fetched over one. Each user row grows a ``consumption`` field holding
        the CUMULATIVE counters alone — the bucket ring is the rebalance's
        private window and never leaves the commander.
        """
        names = self.active_workers
        states = await asyncio.gather(*(self.fetch_monitor_state(name) for name in names))
        workers: list[dict[str, Any]] = []
        for name, state in zip(names, states, strict=True):
            row: dict[str, Any] = {"id": name, "group": self.worker_roster[name]["group"]}
            if state is None:
                row["error"] = "unreachable"
            else:
                users = state.get("users") or []
                for user_row in users:
                    consumption = self.user_consumption.get(user_row.get("register_item_id"))
                    if consumption is not None:
                        user_row["consumption"] = {
                            "requests": consumption["requests"],
                            "seconds": consumption["seconds"],
                        }
                row["users"] = users
                row["connections"] = state.get("connections") or []
                row["pages"] = state.get("pages") or []
            workers.append(row)
        return {"workers": workers}

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

        Every forward is clocked into the worker's cumulative counters
        (``count_forward``) and, when the surface still holds the identity AT
        COUNT TIME, into that user's consumption — around the CALL alone,
        BEFORE the REPLY fold (the legacy order): the fold's own work (placing
        another user's login) stays off this clock and off this identity. The
        membership is read at the count, not before the call, so an identity a
        CONCURRENT fold removed while this forward was in flight is not billed
        back into existence. A CALL that fails in transport is counted as an
        error and re-raised; an error REPLY is a completed forward — its
        exception rises from the drain, after the count.
        """
        worker = await self.resolve_worker(identity)
        request_id = self.open_request(worker, identity, path)
        try:
            start = time.monotonic()
            try:
                payload = await self.hub.call(
                    worker, path, {"identity": identity, "kwargs": kwargs or {}}, timeout=timeout
                )
            except Exception:
                self.count_forward(worker, time.monotonic() - start, error=True)
                raise
            elapsed = time.monotonic() - start
            self.count_forward(worker, elapsed)
            if identity in self.user_worker_map:
                self.count_user_consumption(identity, elapsed)
            result = await self.unwrap_reply(worker, path, payload)
        finally:
            self.close_request(worker, identity, request_id)
        envelope: dict[str, Any] = {"result": result}
        envelope.update({key: payload[key] for key in DELIVERY_KEYS if key in payload})
        return envelope

    async def resolve_worker(self, identity: str) -> str:
        """The worker to route ``identity`` to, once nothing of it is in flight.

        Two holds, both read BEFORE the pick: a move carrying this identity, and
        a placement of it. Either one makes the map's answer provisional, and
        they are read in ONE loop rather than one after the other: a coroutine
        waking from the placement wait may find a move raised meanwhile, and a
        move that lands may be followed by a login raising the flag. The loop
        leaves only when neither is up — and with neither up at the start it
        awaits nothing at all, exactly as before.
        """
        while self.is_held(identity):
            await self.await_move(identity)
            await self.await_placement(identity)
        return self.worker_for(identity)

    def is_held(self, identity: str) -> bool:
        """Whether either hold — a move of this identity, or a placement — is up."""
        return identity in self.moving or self.user_worker_map.get(identity, "") is None

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
        """Where an UNPLACED just-logged user belongs: reception-first.

        Occupancy is the second step of the placement and it only ever sees the
        users nobody holds — ``place_login`` answers the presence question
        before asking this one. The reception KEEPS the login while it stays
        under ``reception_threshold`` (and a sole worker keeps always); over the
        threshold it PASSES to the least loaded of the others that still admit.
        The admission gate never blocks a login: with every other worker over it
        the last one takes the user anyway, under a warning, and growth is
        ``check_capacity``'s business. That check runs AFTER the pick, so a login
        never lands on the worker its own arrival spawned.
        """
        candidates = self.active_workers
        if not candidates:
            raise RuntimeError("no worker available to place a login")
        chosen = self.pick_placement(candidates)
        self.check_capacity()
        return chosen

    def pick_placement(self, candidates: list[str]) -> str:
        """The reception-first pick over ``candidates`` (the active workers)."""
        reception = candidates[0]
        others = candidates[1:]
        if not others or self.evaluator.worker_saturation(reception) < self.reception_threshold:
            return reception
        admitting = [name for name in others if self.evaluator.worker_saturation(name) < 1.0]
        if not admitting:
            fallback = others[-1]
            self.logger.warning(
                "Every worker past the admission gate; placing the login on %s anyway", fallback
            )
            return fallback
        return min(admitting, key=self.evaluator.worker_load)

    def check_capacity(self) -> None:
        """Widen the pool when the login just placed found no room left.

        A pool of one grows when its reception passes ``reception_threshold`` —
        the moment it would start passing logins on. A pool of many grows when no
        NON-reception worker still admits, the reception being the guests' worker
        rather than a placement target. A spawn already in flight is waited for
        instead of being stacked on, and ``max_workers`` is a hard ceiling.
        """
        active = self.active_workers
        if not active:
            return
        reception, others = active[0], active[1:]
        if others:
            if any(self.evaluator.worker_saturation(name) < 1.0 for name in others):
                return
            reason = "no worker past the reception still admits"
        else:
            if self.evaluator.worker_saturation(reception) < self.reception_threshold:
                return
            reason = f"reception {reception} is over its threshold"
        if len(self.living_workers) > len(active):
            return
        if self.max_workers is not None and self.target >= self.max_workers:
            self.logger.warning("Pool full at max_workers=%s; not scaling", self.max_workers)
            return
        self.scale(self.target + 1)
        self.logger.info("%s; scaled to %s", reason.capitalize(), self.target)

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

        A login with NO ``encoded`` is the resident-link announcement: the
        worker that sent it already hosts the user, so it linked the arriving
        connection and shipped nothing. There is no room to make — the user is
        in the one it never left, and the fold raised no flag for it — so the
        event is complete here and never reaches ``place_login``.
        """
        for event in self.fold_events(worker, events):
            if "encoded" not in event:
                continue
            await self.place_login(event["user"], event["encoded"])

    async def place_login(self, user: str, encoded: str) -> None:
        """Give a just-logged user its room: decide, install, map, drop the flag.

        Presence comes BEFORE occupancy: a user already placed goes back to its
        own worker, whatever the load says — the resident half of it is there,
        and ``add_user`` joins the arriving connection onto it. Only a user
        nobody holds is a free choice, and only then does ``decide_worker`` run.

        An unplaced user is flagged in the map (the fold did that) and its slice
        exists only inside ``encoded`` — the source spent its copy pushing it.
        So there is nothing to roll back: an install that fails — the destination
        dying is the only way it can — leaves it nowhere, and the map is made to
        say exactly that. A RESIDENT user is not removed by a failed install:
        the connection that failed to arrive was never its only one, and taking
        the placement away would evict everything that never moved.

        A user being carried is waited for BEFORE the map is read — the same
        hold the exchange path takes. Reading the residence during a move would
        name the source, and the arriving connection would be installed on the
        worker the slice has just left; past the barrier the map names the
        destination and the join lands where the user actually lives.
        """
        await self.await_move(user)
        resident = self.user_worker_map.get(user)
        try:
            destination = resident if resident is not None else self.decide_worker()
            await self.hand_user_to(destination, user, encoded)
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

    # ------------------------------------------------------------------
    # The commander-initiated move: flag, quiesce, custody, switch
    # ------------------------------------------------------------------

    async def move_user(self, user: str, target: str) -> bool:
        """Carry one user's whole slice from where it lives to ``target``.

        FLAG → QUIESCE → evict → install → SWITCH. The flag is a barrier under
        the user's key: every forward of it parks before the pick, so nobody is
        routed at a worker the slice is leaving. The map keeps pointing at the
        SOURCE until the switch — the map's ``None`` is the login's flag and
        this move never touches it.

        The quiesce waits for the user's live calls to finish on the source, and
        no stale entry is ever swept: ``close_request`` runs in a ``finally``
        and a member's EOF fails what was in flight, so an entry that outlives
        its call cannot exist (declared divergence from the legacy sweep). The
        budget expiring aborts the move — the user stays served where it is.

        Past the evict the package exists NOWHERE else: the source stripped
        itself the moment it answered, exactly as it does for a login. So the
        commander holds it in custody and keeps looking for a room — a
        destination that dies mid-install sends the slice to another worker
        (the source included, it is a candidate like any other), and only a pool
        with no worker left at all loses it, loudly.

        Returns whether the user landed on the worker that was ASKED for: a
        salvaged install saved the slice but did not do what the caller wanted,
        and a caller that retires the source on the strength of a move must not
        read that as a drain.
        """
        source = self.user_worker_map.get(user)
        if source is None:
            raise RuntimeError(f"move of {user} is impossible: it is on no worker")
        if user in self.moving:
            raise RuntimeError(f"move of {user} is already in flight")
        self.moving[user] = asyncio.Event()
        try:
            if not await self.quiesce_user(user, source):
                self.logger.warning(
                    "Move of %s from %s aborted: its calls did not drain in %ss",
                    user,
                    source,
                    self.move_quiesce_timeout,
                )
                return False
            try:
                encoded = await self.evict_for_move(user, source)
            except Exception as exc:
                self.logger.warning(
                    "Move of %s from %s aborted (%s: %s)", user, source, type(exc).__name__, exc
                )
                return False
            destination = await self.install_in_custody(user, target, encoded)
            self.assign_user(user, destination)
            self.logger.info("Moved %s from %s to %s", user, source, destination)
            return destination == target
        finally:
            self.release_move(user)

    async def quiesce_user(self, user: str, worker: str) -> bool:
        """Wait for the user's live calls on ``worker`` to drain, within the budget.

        Returns whether the half-row emptied in time. A user with no half-row at
        all has nothing in flight and quiesces at once.
        """
        entry = self.worker_roster[worker]["users"].get(user)
        if entry is None:
            return True
        deadline = time.monotonic() + self.move_quiesce_timeout
        while entry["pending"]:
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(MOVE_QUIESCE_POLL)
        return True

    async def evict_for_move(self, user: str, source: str) -> str:
        """Ask the source for the user's parcel — the one road out of a worker.

        Straight to the hub, never through ``forward_call``: the caller is
        holding this very user's barrier and a forward would park on it.
        """
        path = f"{OP_PATH_PREFIX}evict_user"
        payload = await self.hub.call(source, path, {"identity": user, "kwargs": {}})
        result = await self.unwrap_reply(source, path, payload)
        return str(result["encoded"])

    async def hand_user_to(self, worker: str, user: str, encoded: str) -> Any:
        """Deliver one user's encoded slice to ``worker`` and await its answer.

        The single door of the ``add_user`` handover — the move's custody, the
        login placement and the dump restore all pass through here — so
        ``pending_users`` always knows which worker is sitting on a delivery
        and since when: that is what the caretaker's second eye reads. The
        entry falls with the answer, whatever the answer is.
        """
        path = f"{OP_PATH_PREFIX}add_user"
        self.pending_users.setdefault(worker, time.time())
        try:
            payload = await self.hub.call(
                worker, path, {"identity": user, "kwargs": {"encoded": encoded}}
            )
            return await self.unwrap_reply(worker, path, payload)
        finally:
            self.pending_users.pop(worker, None)

    async def install_in_custody(self, user: str, target: str, encoded: str) -> str:
        """Plant the parcel, re-deciding the room until one takes it.

        The CALL carries no deadline: a REPLY or the destination's EOF ends it,
        and a worker alive but stuck is the caretaker's business, not this
        wait's. Every worker is tried at most once — a pool that refused the
        slice everywhere raises rather than spinning on the same rooms.
        """
        tried: set[str] = set()
        destination: str | None = target
        while destination is not None:
            tried.add(destination)
            try:
                await self.hand_user_to(destination, user, encoded)
            except Exception as exc:
                self.logger.warning(
                    "Install of %s on %s failed (%s: %s); looking for another room",
                    user,
                    destination,
                    type(exc).__name__,
                    exc,
                )
                destination = self.salvage_target(tried)
            else:
                return destination
        raise RuntimeError(f"move of {user} lost its room: no worker left to install it on")

    def salvage_target(self, tried: set[str]) -> str | None:
        """The least loaded active worker no install of this move has burned yet."""
        candidates = [name for name in self.active_workers if name not in tried]
        if not candidates:
            return None
        return min(candidates, key=self.evaluator.worker_load)

    def release_move(self, user: str) -> None:
        """Drop the user's barrier and wake everything parked on it."""
        barrier = self.moving.pop(user)
        barrier.set()

    async def await_move(self, identity: str) -> None:
        """Hold a call whose user is being carried until the move lands.

        One barrier per user, so a move of somebody else never parks this call;
        the registry is re-read on every wakeup, exactly like the placement flag.
        """
        while True:
            barrier = self.moving.get(identity)
            if barrier is None:
                return
            await barrier.wait()

    # ------------------------------------------------------------------
    # The beat: one pass per probe return, rebalance XOR compaction
    # ------------------------------------------------------------------

    def pool_beat(self) -> None:
        """Dispatch the one pass this probe return calls for, if any.

        Excess and slack are the two ways a pool can be wrong, and excess comes
        first: a worker over its own threshold is somebody's latency right now,
        while a pool wider than it needs to be only costs memory. So the presence
        of excess IS the precedence — the two forces never run together, and each
        is single by its own flag.

        "Never together" is read here, once, over BOTH flags: a compaction in
        flight is narrowing the pool the rebalance would shed onto, and a
        rebalance in flight is moving the users the ledger would count. So a
        beat that finds either force up dispatches nothing and lets it finish;
        the XOR only ever chooses what a FREE beat starts.
        """
        if self.compacting or self.rebalancing:
            return
        if self.rebalance_excess():
            self.trigger_rebalance()
        else:
            self.trigger_compaction()

    def worker_threshold(self, worker: str) -> float:
        """The saturation ``worker`` is judged at: its own if reception, else the gate.

        The reception carries the guests as well, so it is asked to stay lower —
        the same asymmetry the capacity ledger counts it with.
        """
        return self.reception_threshold if worker == self.reception else 1.0

    def rebalance_excess(self) -> list[tuple[str, float]]:
        """Every worker over its OWN threshold, with by how much, hottest first.

        Saturation, not load: what a shed relieves is the binding resource, which
        is the max.
        """
        excess = []
        for name in self.active_workers:
            over = self.evaluator.worker_saturation(name) - self.worker_threshold(name)
            if over > 0:
                excess.append((name, over))
        return sorted(excess, key=lambda item: -item[1])

    def trigger_rebalance(self) -> None:
        """Start a rebalance pass unless one is already in flight."""
        if self.rebalancing:
            return
        self.rebalancing = True
        try:
            self.spawn_pool_pass(self.rebalance_pass())
        except Exception:
            self.rebalancing = False
            raise

    def trigger_compaction(self) -> None:
        """Start a compaction pass unless one is already in flight."""
        if self.compacting:
            return
        self.compacting = True
        try:
            self.spawn_pool_pass(self.compact_pass())
        except Exception:
            self.compacting = False
            raise

    def spawn_pool_pass(self, pass_coroutine: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """Run one pool pass detached: the beat never waits on what it started.

        The loop holds only a weak reference to a task, so the set is what keeps
        the pass alive; the caretaker that dispatched it goes back to its cadence.
        """
        task = asyncio.create_task(pass_coroutine)
        self._pool_tasks.add(task)
        task.add_done_callback(self._pool_tasks.discard)
        task.add_done_callback(self.log_task_error)
        return task

    async def rebalance_pass(self, now: float | None = None) -> None:
        """Shed the excess of the hot workers onto the ONE worker that has room.

        The total excess is read once, at the start: the target has to absorb all
        of it, so it is picked against the sum rather than against the worker
        being relieved. No target able to take it — nobody is cool enough, or
        every other worker is hot too — and the pass widens the pool instead and
        ends: the next beat finds a fresh, empty worker and sheds onto that.

        With a target, each hot worker from the hottest down hands over the users
        ``pick_rebalance_users`` names for it, one whole ``move_user`` each. A move
        that does not land ENDS the pass: the pool just changed under the readings
        this pass was decided on. Nothing is ever retired here — a rebalance
        levels the pool, only the compaction narrows it.
        """
        try:
            excess = self.rebalance_excess()
            if not excess:
                return
            target = self.pick_rebalance_target(sum(value for _, value in excess))
            if target is None:
                self.rebalance_spawn()
                return
            for worker, budget in excess:
                target_empty = not self.users_on(target)
                for user in self.pick_rebalance_users(worker, budget, target_empty, now):
                    if self.user_worker_map.get(user) != worker:
                        continue
                    if not await self.move_user(user, target):
                        self.logger.warning(
                            "Rebalance of %s: %s did not land on %s, ending the pass",
                            worker,
                            user,
                            target,
                        )
                        return
        finally:
            self.rebalancing = False

    def pick_rebalance_target(self, total_excess: float) -> str | None:
        """The one worker that absorbs the whole excess, or None when nobody can.

        A candidate is a NON-reception worker that is not hot itself and whose
        saturation still sits under ``1.0 - rebalance_margin`` once the whole
        excess has landed on it — a target filled up to the gate would be the next
        beat's hot worker. Among those the least LOADED wins: the fit is judged on
        the binding resource, the choice on the whole picture.
        """
        ceiling = 1.0 - self.rebalance_margin
        saturation = self.evaluator.worker_saturation
        eligible = [
            name
            for name in self.active_workers[1:]
            if saturation(name) <= self.worker_threshold(name)
            and saturation(name) + total_excess <= ceiling
        ]
        if not eligible:
            return None
        return min(eligible, key=self.evaluator.worker_load)

    def rebalance_weights(self, worker: str, now: float | None = None) -> dict[str, float]:
        """``worker``'s saturation apportioned over its MOVABLE users, by recent seconds.

        The share is a user's recent service time over what the whole worker
        served (guests included: their cost is the worker's, and pretending
        otherwise would inflate everybody else's share), and the weight is that
        share of the worker's saturation — the same currency as the excess and the
        budget, so the wall-time inflation cancels in the ratio.

        Only the users the map places HERE come back weighted: a guest is on no
        map and never moves (its sticky identity lives on the reception), and a
        user that already left is not this worker's to shed. A worker whose users
        served nothing recently weighs nothing: there is no excess of theirs to
        move.
        """
        seconds = {user: self.user_recent_seconds(user, now) for user in self.users_on(worker)}
        total = sum(seconds.values())
        if total <= 0.0:
            return {}
        saturation = self.evaluator.worker_saturation(worker)
        return {
            user: saturation * (value / total)
            for user, value in seconds.items()
            if self.user_worker_map.get(user) == worker
        }

    def pick_rebalance_users(
        self, worker: str, budget: float, target_empty: bool, now: float | None = None
    ) -> list[str]:
        """Which users of ``worker`` to shed to cover ``budget``, in the order to move.

        Toward an EMPTY target the HEAVIEST go first: the fewest moves, and a
        container with nothing in it absorbs the estimate error. Toward a LOADED
        one the LIGHTEST go first, and only among the users carrying at least
        ``rebalance_min_share`` of the worker — a nearly idle user sheds nothing
        and the move would cost a whole slice on the wire. Users accumulate until
        their weights cover the budget, or until there are none left.
        """
        weights = self.rebalance_weights(worker, now)
        if not weights:
            return []
        if target_empty:
            ordered = sorted(weights, key=lambda user: -weights[user])
        else:
            floor = self.rebalance_min_share * self.evaluator.worker_saturation(worker)
            ordered = sorted(
                (user for user in weights if weights[user] >= floor),
                key=lambda user: weights[user],
            )
        picked: list[str] = []
        shed = 0.0
        for user in ordered:
            if shed >= budget:
                break
            picked.append(user)
            shed += weights[user]
        return picked

    def rebalance_spawn(self) -> None:
        """Widen the pool by one because a hot worker has nowhere to shed.

        The scale-up's own guards: a worker already on its way is waited for
        instead of being stacked on, and ``max_workers`` is a hard ceiling. The
        pass ends here either way — the fresh worker is cold and empty, which is
        exactly the target the next beat needs.
        """
        if len(self.living_workers) > len(self.active_workers):
            return
        if self.max_workers is not None and self.target >= self.max_workers:
            self.logger.warning(
                "Pool full at max_workers=%s; the rebalance cannot spawn", self.max_workers
            )
            return
        self.scale(self.target + 1)
        self.logger.info("A hot worker has no absorber; scaled to %s", self.target)

    # ------------------------------------------------------------------
    # Compaction: the capacity ledger, and the workers it folds away
    # ------------------------------------------------------------------

    def capacity_headroom(self) -> float:
        """The ledger ``C - O``: how much room the pool has beyond what it holds.

        ``C`` is what the pool may take — the reception up to its own threshold
        plus a whole gate for every other worker — and ``O`` is what it holds,
        summed in QUANTITY (``worker_load``): the ledger asks how much fits, not which
        resource binds. A pool with no active worker has no capacity to report.
        """
        active = self.active_workers
        if not active:
            return 0.0
        capacity = self.reception_threshold + (len(active) - 1) * 1.0
        occupied = sum(self.evaluator.worker_load(name) for name in active)
        return capacity - occupied

    async def compact_pass(self) -> None:
        """Fold workers away while the pool has room to spare, one at a time.

        The ledger decides how many: while the headroom stays over
        ``compaction_margin`` — one whole gate being 1.0 — the least loaded
        NON-reception worker is drained and retired. The reception is never a
        candidate: it is the guests' worker, the one address a pool always has.
        A drain that does not empty its worker STOPS the pass and retires
        nothing: a worker still holding state is never retired.
        """
        try:
            while True:
                active = self.active_workers
                candidates = active[1:]
                if not candidates or len(active) <= self.min_workers:
                    return
                if self.capacity_headroom() <= self.compaction_margin:
                    return
                candidate = min(candidates, key=self.evaluator.worker_load)
                if not await self.drain_worker(candidate):
                    self.logger.warning(
                        "Compaction stopped: worker %s did not drain, keeping it", candidate
                    )
                    return
                self.retire(candidate)
                self.logger.info(
                    "Compaction retired worker %s; target is %s", candidate, self.target
                )
        finally:
            self.compacting = False

    async def drain_worker(self, worker: str) -> bool:
        """Move every user off ``worker``; returns whether it ended up empty.

        Each user goes to its own admission-rule target, decided one move at a
        time: the previous arrival changed what the pool reads. A user that left
        by itself in the meantime — swept with a death, or moved by somebody else
        — is nobody's move any more. One refused move ends the drain: the caller
        retires on the strength of this answer.
        """
        for user in sorted(self.users_on(worker)):
            if self.user_worker_map.get(user) != worker:
                continue
            target = self.pick_compaction_target(worker)
            if target is None:
                self.logger.warning("Drain of %s: no other worker to take %s", worker, user)
                return False
            if not await self.move_user(user, target):
                return False
        return not self.users_on(worker)

    def pick_compaction_target(self, drained: str) -> str | None:
        """Where one user of ``drained`` belongs: the admission rule, once.

        The least loaded worker that still admits, and the least loaded of all if
        none does — the ledger already promised the pool fits, so a gate closed
        everywhere is a reading in flight, not a reason to abandon the user.
        None only when ``drained`` is the whole pool.
        """
        candidates = [name for name in self.active_workers if name != drained]
        if not candidates:
            return None
        admitting = [name for name in candidates if self.evaluator.worker_saturation(name) < 1.0]
        return min(admitting or candidates, key=self.evaluator.worker_load)
