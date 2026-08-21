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
  occupancy, floors, floor_readings, caretaker}``.
  ``status`` walks ``nascent`` (spawned, not yet presented) →
  ``active`` (REGISTER seen) → [``retiring`` (a plan in flight names it for a
  replace or a compact: it still serves who it holds and still counts toward the
  target, but it is never a destination again)] → [``evacuating`` (being
  condemned: its users are being carried over, and it is out of every picker
  while it still serves whoever remains — with a successor already up on the
  replace branch, with none at all when the weight gate opened ``spawn=False``
  and the pool narrows by one)] → ``draining`` (deliberately retired) →
  ``dead`` — except a nascent one, which jumps straight to ``dead`` when culled
  or retired (no channel means no drain to complete); ``died_at``/``death``
  (``retired``/``crash``/``stillborn``) are the tombstone stamps
  ``bury_workers`` reads;
  ``users`` maps each held user to ``{pending, last_activity_ts, occupancy}``
  (``pending`` is that user's live calls, ``occupancy`` a field the future
  evaluator fills — 2a never computes it); ``occupancy`` is the window of the
  last ``METRICS_WINDOW`` raw reports the probe collected (the commander
  archives, judging belongs to the evaluator); ``floors`` is the long memory
  beside it — one live-memory floor per closed window, up to
  ``floor_series_depth`` of them, with ``floor_readings`` counting toward the
  next sample (issue #8); ``caretaker`` is that worker's
  own probe task, ``None`` when it has none. A user's routing group is its
  worker's ``group``, read from the row.
- ``user_worker_map`` — user identity → its PLACEMENT: the name of the worker
  holding it, or ``FROZEN`` when its slice is hibernated to a file in
  ``frozen_users_dir`` and no worker holds it (absent means unplaced). It
  is the ONLY structure that says WHERE a user is, and both it and the rows
  mutate through the single pair ``assign_user`` / ``remove_user``.
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
swept. That is why a move needs nothing up here
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
all; a page the surface cannot resolve simply misses it.

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

**One fold, one drain.** ``place_logins(worker, events)`` applies the events a
REPLY carried, in the order they were delivered — they are the lifecycle the
answered CALL itself caused, so there is nothing to deduplicate and no
watermark to keep — and SETTLES each login among them on the same tick. The
drain runs in the commander, never in the transport: ``unwrap_reply`` folds
the ``events`` of the payload before reading its ``result``/``error``, and the
CALL-less rail (``fold_command``) folds one event at a time through the same
``fold_event``. The owner check is the only guard, and it is the legacy rule:
a late event never re-points a user already assigned elsewhere; only the
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

**The login decides, the move executes** (ratified 2026-08-12). The worker
never ships at login: its ``change_connection_user`` event announces the
re-label and the slice stays where it is — the request that carried the login
keeps finding its pages there to the end. The fold, in the caller's own
coroutine, settles each login BEFORE the caller is released, and the answer is
the map: a user nobody holds is mapped to the worker that announced it — THE
MAP IS WRITTEN AT THE DECISION (the founding contract), and the decision is
"the user lives where it logged in". Then ``decide_worker`` (reception-first)
says whether it BELONGS somewhere else, and a user that does is handed to the
ordinary commanded move as a DETACHED task: the response never waits for the
transfer — the move's own ``moving`` hold parks whatever arrives for that user
during the handful of milliseconds the quiesce-evict-install takes (the
quiesce is near-instant: the causing call just closed). A user already
resident on the announcing worker was joined there and nothing else happens.
A user resident on ANOTHER worker is not a move at all: a detached task
materializes the arriving connection at the residence and discards the remnant
at the announcing worker (operational evict, parcel dropped) — the resident
wins, and what the guest did before logging in dies with the remnant, loudly,
never silently (declared extension of the guest-carry boundary). A failed
move task is the move machinery's own business: custody, salvage, at worst
the user stays where it is and the ordinary rebalance retries later.

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

**The pool's shape is decided by a PLAN, built from ONE reading, on its own
clock.** The ``planner`` task wakes every ``decision_interval`` — minutes, not
seconds — and asks ``build_plan`` for the ordered list of steps the pool as it
then reads calls for: at most one rebalance, then one replacement per condemned
worker — the NECESSITY candidates first (a live-memory floor that has reached
its budget), then the CONVENIENCE ones most wasteful first — then the
compaction, emptiest worker first. ``execute_plan`` runs them in that order, one
at a time, and the plan as a whole is the ONE operation in flight: it stands in
``active_plan`` for the whole run, and a tick landing mid-plan builds nothing.
The probes decide nothing: they carry health and the numbers at 5s, and the real
emergencies stay on the fast reflexes (the caretaker's kill, ``channel_lost``,
the reconcile's respawn).
The compaction reads the capacity ledger — ``C`` what the pool may take (the
reception up to its threshold, a whole gate each for the others), ``O`` what it
holds in ``worker_load`` — and takes a worker only while ``C - O`` READ WITHOUT
it stays over ``compaction_margin``. The step drains it with ``move_user`` and
retires it; a drain that does not empty retires nothing, because a worker still
holding state is never retired.
A replacement spawns a fresh worker only when the rest of the pool cannot
absorb the condemned one's users with margin — the condemnation in
``build_plan`` reads the two criteria in the open: the margin left on the
ledger once the condemned and the other leavers are out
(``workers_occupancy_metric``), and every user individually placeable
(``pick_best_fit``). With the room already there the worker is condemned and
evacuated without a new process, and the pool narrows by one. Condemning the reception always spawns — that is role
continuity, not capacity.

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
import urllib.parse
import uuid
from collections import deque
from collections.abc import Coroutine, Sequence
from pathlib import Path
from typing import Any

from genro_storage import StorageNode
from genro_tytx import from_tytx, to_tytx

from ..channel.frame import Frame
from ..channel.hub import ChannelCallError, ChannelHub, ChannelMember
from ..channel.local import LocalChannel
from ..exceptions import HTTPException
from .evaluator import OccupancyEvaluator
from .global_store import (
    GLOBAL_CHANGES_PATH,
    GLOBAL_GRANT_PATH,
    GLOBAL_SNAPSHOT_PATH,
    CapturingGlobalStore,
    GlobalStoreLock,
)
from .register_registry import GUEST_PREFIX
from .subscription_index import SubscriptionIndex
from .worker import (
    CONNECTION_MAX_AGE,
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
    "DECISION_INTERVAL",
    "DEFAULT_GROUP",
    "EVACUATION_WARN_INTERVAL",
    "FLOOR_LIMIT_RATIO",
    "FLOOR_SERIES_DEPTH",
    "FREEZE_IDLE_AFTER",
    "FREEZE_IDLE_FLOOR",
    "FROZEN",
    "FROZEN_GUEST_LIFETIME",
    "FROZEN_USER_LIFETIME",
    "MAX_PENDING_CYCLES",
    "METRICS_WINDOW",
    "MOVE_QUIESCE_TIMEOUT",
    "PROBE_INTERVAL",
    "PROBE_TIMEOUT",
    "REBALANCE_MARGIN",
    "REBALANCE_MIN_SHARE",
    "RECEPTION_THRESHOLD",
    "RECYCLE_HORIZON_HOURS",
    "SPAWN_MARGIN",
    "TOMBSTONE_SECONDS",
    "UserStickyCommander",
    "WASTE_RATIO",
]

#: The single routing group of 2a: the group column exists everywhere, the
#: groups feature does not. PROVISIONAL — it becomes per-group configuration.
DEFAULT_GROUP = "default"

#: How many raw occupancy reports are kept per worker (~5 minutes at one probe
#: every 5s). PROVISIONAL, transcribed from the legacy commander.
METRICS_WINDOW = 60

#: How many live-memory FLOORS are kept per worker (issue #8). One floor is
#: sampled per full ``METRICS_WINDOW`` of readings — ~5 minutes each, so 72 of
#: them span ~6 hours, the horizon a leak has to show itself over.
FLOOR_SERIES_DEPTH = 72

#: The per-user consumption window: a ring of ``CONSUMPTION_BUCKETS`` slots of
#: ``CONSUMPTION_BUCKET_SECONDS`` each — 6 buckets of 5s = a ~30s window, the
#: mirror of the evaluator's smoothing window. ``user_recent_seconds`` sums the
#: buckets still inside it. PROVISIONAL, transcribed from the legacy commander.
CONSUMPTION_BUCKET_SECONDS = 5.0
CONSUMPTION_BUCKETS = 6

#: Seconds between two probes of the same worker. PROVISIONAL — it becomes
#: per-group configuration.
PROBE_INTERVAL = 5.0

#: How often the ``planner`` reads the whole pool and runs the plan that reading
#: calls for. The shape of a pool is not an emergency: it is decided on its own
#: slow clock, minutes apart, while the probes keep their 5s health cadence.
#: PROVISIONAL — it becomes per-group configuration.
DECISION_INTERVAL = 300.0

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
#: anti-ping-pong margin — a target filled right up to the gate would be the hot
#: worker of the next planner tick. PROVISIONAL — it becomes per-group configuration.
REBALANCE_MARGIN = 0.1

#: How often a stalled evacuation is reported again while it stays stalled. A
#: sysop cadence, not a connection clock: the condition does not change from one
#: planner tick to the next, and the report is for a human. PROVISIONAL.
EVACUATION_WARN_INTERVAL = 300.0

#: The placement of a user parked on disk: ``user_worker_map`` holds a worker
#: name, or nothing at all while the user is being assigned, or THIS. It cannot
#: collide with a worker name, which always carries the ``W:`` prefix.
FROZEN = "frozen"

#: How long a user must sit idle before the freezer parks it on disk, at a
#: worker with no memory pressure at all. The valve shortens it as the pressure
#: rises — see ``freeze_candidates``. PROVISIONAL — it becomes per-group
#: configuration (issue #18), and it is the value a deployment arms
#: ``freeze_idle_after`` with: the kwarg itself defaults to None, the freezer
#: disarmed, because no instance name reaches this layer to derive a parcel
#: directory from.
FREEZE_IDLE_AFTER = 1800.0

#: The shortest wait the valve may come down to, whatever the memory pressure:
#: a user that answered seconds ago is not hibernated because its worker is
#: full. PROVISIONAL — it becomes per-group configuration (issue #18).
FREEZE_IDLE_FLOOR = 300.0

#: How long a GUEST's parcel is kept in the freezer before ``reap_frozen_files``
#: deletes it: the guest cookie's own day, after which nobody can come back for
#: it anyway. The class is read off the parcel's name, which carries
#: ``GUEST_PREFIX`` by construction. PROVISIONAL — the per-class lifetimes become
#: configuration together with the cookie ages (issue #18).
FROZEN_GUEST_LIFETIME = 86400.0

#: How long a logged user's parcel is kept in the freezer: a week, long enough
#: for a Monday to find what Friday hibernated. PROVISIONAL, as above.
FROZEN_USER_LIFETIME = 604800.0

#: The comfort horizon the floor TREND is read against (issue #8): how many hours
#: from the memory limit a worker's live-memory floor counts as heading for it.
#: An OBSERVATION parameter — the replacement decides on current measures (R5),
#: never on the projection, so nothing is condemned by this number; the monitor's
#: photograph is its only reader. PROVISIONAL — it becomes per-group
#: configuration.
RECYCLE_HORIZON_HOURS = 12.0

#: How close to its memory limit a worker's live-memory floor may sit before the
#: pool replaces it out of NECESSITY: the floor is what the process will not give
#: back, so a floor at this share of the limit is a worker that has already spent
#: its budget. PROVISIONAL — it becomes per-group configuration.
FLOOR_LIMIT_RATIO = 0.8

#: How much memory a worker may hold beyond its live floor before the pool
#: replaces it out of CONVENIENCE: the waste is what the process keeps without
#: using it, measured against the floor it actually needs. 0.5 is "half again as
#: much as it needs". PROVISIONAL — it becomes per-group configuration.
WASTE_RATIO = 0.5

#: How little free capacity — in whole admitting workers — the pool may be left
#: with before a spawn is due even when no worker is hot. Lower than
#: ``COMPACTION_MARGIN`` by construction: the band between the two is where the
#: pool neither folds nor widens, and without it every fold would be undone by
#: the spawn that follows. PROVISIONAL — it becomes per-group configuration.
SPAWN_MARGIN = 0.5

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

#: The lifecycle op that is a login: the sticky key changes and a settle is due.
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
        decision_interval: float = DECISION_INTERVAL,
        max_pending_cycles: int = MAX_PENDING_CYCLES,
        local_worker: bool = False,
        dump_path: str | None = None,
        memory_limit_mb: int | None = None,
        admission_threshold: float = 0.8,
        component_targets: dict[str, float] | None = None,
        reception_threshold: float = RECEPTION_THRESHOLD,
        move_quiesce_timeout: float = MOVE_QUIESCE_TIMEOUT,
        compaction_margin: float = COMPACTION_MARGIN,
        spawn_margin: float = SPAWN_MARGIN,
        rebalance_margin: float = REBALANCE_MARGIN,
        rebalance_min_share: float = REBALANCE_MIN_SHARE,
        floor_series_depth: int = FLOOR_SERIES_DEPTH,
        recycle_horizon_hours: float = RECYCLE_HORIZON_HOURS,
        floor_limit_ratio: float = FLOOR_LIMIT_RATIO,
        waste_ratio: float = WASTE_RATIO,
        freeze_idle_after: float | None = None,
        freeze_idle_floor: float = FREEZE_IDLE_FLOOR,
        frozen_users_dir: StorageNode | None = None,
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
        decision_interval: seconds between two readings of the pool by the
            ``planner`` — the cadence the pool's shape is decided on.
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
        spawn_margin: the headroom under which a spawn is due even with no hot
            worker. Strictly under ``compaction_margin`` — the band between the
            two is where the pool neither folds nor widens.
        rebalance_margin: how far under the gate a rebalance leaves its target
            once it has absorbed the whole excess — the anti-ping-pong margin.
        rebalance_min_share: the smallest share of its worker's saturation a user
            must carry to be shed onto a LOADED target.
        floor_series_depth: how many live-memory floors are kept per worker — the
            long series the recycling trend is read off (issue #8). One floor per
            full ``METRICS_WINDOW`` of readings.
        recycle_horizon_hours: how close to the memory limit a worker's floor may
            be heading — in hours left — before the trend counts as heading for it
            (issue #8). Read by the monitor's photograph only: it condemns nobody.
        floor_limit_ratio: the share of ``memory_limit_mb`` a worker's live-memory
            floor may reach before its replacement is a NECESSITY.
        waste_ratio: how much a worker may hold beyond its live floor, as a share
            of that floor, before its replacement is a CONVENIENCE.
        freeze_idle_after: how long a user may sit idle before the freezer parks
            it on disk, at a worker under no memory pressure (``FREEZE_IDLE_AFTER``
            is the provisional value to arm it with). None disarms the freezer.
        freeze_idle_floor: the shortest wait the memory valve may bring that
            number down to.
        frozen_users_dir: where the freezer writes its parcels, one file per
            user — a storage node (e.g. ``storage.node("GENROASGI:frozen_users")``),
            so the destination is a logical mount, never a raw path. Required
            whenever ``freeze_idle_after`` is set: no instance name reaches
            this layer, so a directory cannot be derived without one.
        """
        if spawn_margin >= compaction_margin:
            raise ValueError(
                "spawn_margin must stay under compaction_margin, "
                f"got {spawn_margin} >= {compaction_margin}"
            )
        self.target = workers
        self.group = group
        self.worker_class = worker_class
        self.worker_kwargs = dict(worker_kwargs or {})
        self.executable = executable or sys.executable
        self.max_workers = max_workers
        self.reception_threshold = reception_threshold
        self.probe_interval = probe_interval
        self.probe_timeout = probe_timeout
        self.decision_interval = decision_interval
        self.max_pending_cycles = max_pending_cycles
        self.local_worker = local_worker
        self.dump_path = dump_path
        self.memory_limit_mb = int(memory_limit_mb) if memory_limit_mb is not None else None
        self.move_quiesce_timeout = move_quiesce_timeout
        self.compaction_margin = compaction_margin
        self.spawn_margin = spawn_margin
        self.rebalance_margin = rebalance_margin
        self.rebalance_min_share = rebalance_min_share
        self.floor_series_depth = floor_series_depth
        self.recycle_horizon_hours = recycle_horizon_hours
        self.floor_limit_ratio = floor_limit_ratio
        self.waste_ratio = waste_ratio
        self.freeze_idle_after = freeze_idle_after
        self.freeze_idle_floor = freeze_idle_floor
        if frozen_users_dir is None and freeze_idle_after is not None:
            raise ValueError(
                "freeze_idle_after is armed but frozen_users_dir is not given, and "
                "no instance name reaches the commander to derive one from: two "
                "instances sharing a directory would wake each other's users"
            )
        self.frozen_users_dir = frozen_users_dir
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
        # The whole surface: one row per worker, one entry per user. The map is
        # written at the DECISION — for a login, "the user lives where it
        # logged in", stamped by the fold itself.
        self.worker_roster: dict[str, dict[str, Any]] = {}
        self.user_worker_map: dict[str, str] = {}
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
        # The users a commander-initiated move is carrying right now, each with
        # the barrier every forward of that user parks on until it lands. Since
        # the login stopped shipping (2026-08-12) this is the ONLY hold there is.
        self.moving: dict[str, asyncio.Event] = {}
        # One handover at most is in flight toward a worker — BY CONSTRUCTION,
        # not by assumption (issue #15: an evacuation's burst of call-close
        # moves all aims at one compaction target): worker -> when its
        # unanswered add_user CALL left.
        # Written and cleared by hand_user_to, read by the caretaker (#9).
        self.pending_users: dict[str, float] = {}
        # The removalist of each destination: one delivery at a time per
        # worker — hand_user_to queues on it. Minted on first delivery,
        # buried with the roster row.
        self.removalists: dict[str, asyncio.Lock] = {}
        # The pool-shape work in flight: the ordered steps of the plan being
        # executed, None when idle. One plan at a time (one pool, one shape),
        # and the task set is what keeps its pass alive.
        self.active_plan: list[dict[str, Any]] | None = None
        # Whether the pool can still take strangers in: ``ready`` normally,
        # ``restricted`` from the moment a plan aborted because no fresh worker
        # would register. A STATE of the pool, not of any request — the first
        # REGISTER that lands is the positive proof that ends it.
        self.pool_status = "ready"
        self._pool_tasks: set[asyncio.Task[None]] = set()
        self._reconcile_task: asyncio.Task[None] | None = None
        self._planner_task: asyncio.Task[None] | None = None
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
        """The names of the workers currently connected, in spawn order.

        A ``retiring`` one is still here: a plan has named it, but until its own
        step runs it serves who it holds and counts in every picture. What it is
        not is a DESTINATION — the placement rules exclude it by name.
        """
        return [
            name
            for name, entry in self.worker_roster.items()
            if entry["status"] in ("active", "retiring")
        ]

    @property
    def living_workers(self) -> list[str]:
        """The names of the workers that count toward the target.

        ``nascent`` + ``active`` + ``retiring``: a worker a plan has condemned
        still holds its process and its users, so the reconcile must not read it
        as a shortfall and spawn a second one beside it.
        """
        return [
            name
            for name, entry in self.worker_roster.items()
            if entry["status"] in ("nascent", "active", "retiring")
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

        Two periodic tasks are started here: the reconcile, which keeps the
        pool's SIZE at the target, and the planner, which decides its SHAPE.

        The dump of the previous run is read back LAST, when there is a pool to
        install it on.
        """
        await self.hub.start()
        if self.local_worker:
            await self.attach_local_worker()
        self._reconcile_task = asyncio.create_task(self.reconcile_loop())
        self._planner_task = asyncio.create_task(self.planner())
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

        The retire walks every roster row that is not dead — wider than
        ``living_workers``, whose nascent+active membership is the reconcile's
        shortfall math and stays untouched. A worker mid-recycling
        (``evacuating``) or already ``draining`` has a live process that this
        stop must still signal and await; only the tombstones have nothing
        left to end. A plan caught in flight is released FIRST, so the retire
        walk finds plain rows rather than the stamps of a plan nobody will run.
        A ``restricted`` pool goes back to ``ready`` here too: the restriction
        described a pool that could not regenerate, and this one is closing.
        """
        if self.active_plan is not None:
            self.release_plan()
        self.pool_status = "ready"
        await self.write_dump()
        for task in (self._reconcile_task, self._planner_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._reconcile_task = None
        self._planner_task = None
        self.target = 0
        retired = [
            name for name, entry in self.worker_roster.items() if entry["status"] != "dead"
        ]
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

        A frozen user is skipped: its parcel is already a file, and asking for
        it would only wake it onto a worker this very method is emptying.
        """
        if self.dump_path is None:
            return
        packages: dict[str, str] = {}
        for user in list(self.user_worker_map):
            if self.user_worker_map[user] == FROZEN:
                continue
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

        Only a living worker (``nascent``, ``active`` or ``retiring``) is
        retirable: a draining or evacuating one is already on its way out (the
        recycling retires its source itself), and a dead one is a tombstone —
        flipping it back to ``draining`` would make it unburiable (its
        ``channel_lost`` already fired) and shrink the target for a corpse.
        ``retiring`` is in because a compaction step retires exactly the worker
        its own plan stamped on the way in.
        """
        entry = self.worker_roster.get(name)
        if entry is None:
            raise KeyError(f"no such worker to retire: {name!r}")
        if entry["status"] not in ("nascent", "active", "retiring"):
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
            self.removalists.pop(name, None)

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
        """Ask one worker for its occupancy and archive it: health, nothing more.

        The probe is the proof of life and the source of the numbers, at 5s. It
        decides no shape: the pool is read whole by the ``planner`` on its own
        slow clock (R1), so an archived report waits there instead of pulling a
        move behind itself.

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

        ``floors`` is the long memory next to the short one: one ``{ts, floor}``
        live-memory floor per full window of readings, ``floor_readings``
        counting toward the next sample. The occupancy window says how full the
        worker is now; the floor series says where it is heading (issue #8).
        ``evacuating_since`` stamps the moment a recycling flags this worker —
        an evacuation is a state that converges, and the stamp is what lets a
        stalled one (a straggler past the pool's own inactivity clocks) be told
        apart and reported; ``evacuation_warned_at`` throttles that report.
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
            "floors": deque(maxlen=self.floor_series_depth),
            "floor_readings": 0,
            "evacuating_since": None,
            "evacuation_warned_at": None,
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

        A REGISTER is also the one POSITIVE PROOF that the pool can regenerate,
        so it is what lifts a ``restricted`` pool: whatever refused to start
        when the plan aborted, a child has just presented itself, and the door
        opens again for the strangers that were being turned away.
        """
        entry = self.worker_roster.get(member.name)
        if entry is None:
            self.logger.warning("Foreign member on the commander hub: %s", member.name)
            return
        entry["status"] = "active"
        if self.pool_status != "ready":
            self.pool_status = "ready"
            self.logger.info("Pool ready again: %s registered", member.name)
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

        Only ``draining`` reads as deliberate: a worker dying while
        ``evacuating`` died mid-evacuation, so it is a crash and its remaining
        users are swept and re-placed like any other death's.
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
            self.fold_event(worker, message)
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

        An address the surface cannot resolve — an unknown page, a target
        already swept — is dropped with a debug log: a change is a signal and
        there is no retry queue (the legacy rule, verbatim). A ``connection_store`` target is a session id, resolved in
        two hops along the ownership chain — ``connection_user`` then
        ``user_worker_map`` — since a connection lives where its user lives.

        A ``FROZEN`` placement is as unroutable as a missing one and drops the
        same way: the user's pages are in a file, so no worker holds them, and a
        change is a signal with no retry queue.
        """
        if message["filters"] is not None:
            return [
                (worker, {**message, "target": page_id, "filters": None})
                for page_id, worker in self.matching_pages(message["filters"])
                if worker is not None and worker != FROZEN
            ]
        target = message["target"]
        if message["kind"] == "user_store":
            worker = self.user_worker_map.get(target)
        elif message["kind"] == "connection_store":
            user = self.connection_user.get(target)
            worker = None if user is None else self.user_worker_map.get(user)
        else:
            worker = self.page_worker(target)
        if worker == FROZEN:
            worker = None
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
        user's residence: all three links of one chain, so the surface holds no
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
        the ``worker`` stamp on the message is what says which. A page the
        surface cannot resolve is skipped too: a dbevent is a signal and there
        is no retry queue — and a page whose user is FROZEN resolves to no
        worker at all, its subscriptions waiting in a file. Deposits sharing a
        destination worker are batched, so a commit reaching N pages of one
        worker costs ONE send.
        """
        origin = message.get("worker")
        buffer: dict[str, list[dict[str, Any]]] = {}
        for deposit in message.get("deposits") or []:
            for page_id in self.page_subscriptions.pages_for(deposit["table"]):
                worker = self.page_worker(page_id)
                if worker is None or worker == FROZEN or worker == origin:
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
        class runs first, and a login it folds is SETTLED here, in the caller's
        own coroutine: the map is stamped, and any transfer the decision calls
        for leaves as a detached task before the caller is released. The TASK
        class is then handed one task per command: the caller waits on none of
        it. An error payload becomes the exception the caller expects — its
        tasks are spawned all the same, since the worker already drained what
        they carry and the op outcome gates neither them nor the delivery.
        """
        self.place_logins(worker, payload.get("events") or [])
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
            self.register_connection(event["connection_id"], event["user"])
        elif op == "drop_connection":
            self.drop_connection(event["connection_id"])
        elif op == LOGIN_OP:
            self.relabel_user(event["user"], event.get("previous_user"), event["connection_id"], worker)
        elif op == "new_page":
            self.register_page(event["page_id"], event["user"], worker, event["connection_id"])
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

    def register_connection(self, connection_id: str, user: str) -> None:
        """Map a connection to the user it belongs to — the middle link, folded."""
        self.connection_user[connection_id] = user
        self.user_connections.setdefault(user, set()).add(connection_id)

    def drop_connection(self, connection_id: str) -> None:
        """Forget one connection: its pages announced their own drop before it.

        The cascade climbs on the worker and is announced in that order, so by
        the time this arrives the pages of that connection are already gone.
        The user stays: a sibling connection of it is being served all along.
        """
        owner = self.connection_user.pop(connection_id, None)
        if owner is not None:
            self.discard_connection_edge(owner, connection_id)
        self.connection_pages.pop(connection_id, None)

    def discard_connection_edge(self, user: str, connection_id: str) -> None:
        """Take one connection off its user's edge set, dropping the set when empty.

        Called only for an owner just read off ``connection_user``, so the edge
        set exists by the alignment invariant — a missing one is a broken
        surface and raises (``KeyError``), never passes silently.
        """
        siblings = self.user_connections[user]
        siblings.discard(connection_id)
        if not siblings:
            del self.user_connections[user]

    def relabel_user(self, user: str, previous_user: str | None, connection_id: str, worker: str) -> None:
        """The login: the CONNECTION changes owner, and no page edge ever moves.

        One edge moves, and one only — the surface transcribes what the worker
        did to its own registers: the connection leaves its guest entry and joins
        the real user's. The pages of that connection follow it without being
        touched, because their user is derived from it and never written. The old
        guest leaves the surface once it has no connection left, and by then it
        owns no page either, BY CONSTRUCTION.

        The slice never moved (the login stopped shipping, 2026-08-12), so a
        user nobody holds is mapped HERE, to the worker that announced it — the
        map is written at the decision, and the decision is "the user lives
        where it logged in". Whether it BELONGS somewhere else is
        ``settle_login``'s question, asked right after the fold. A user already
        placed somewhere keeps its map untouched: it is at home, and the
        announcing worker is either that home (the join) or the holder of a
        remnant ``settle_login`` is about to discard.
        """
        former_owner = self.connection_user.get(connection_id)
        if former_owner is not None and former_owner != user:
            self.discard_connection_edge(former_owner, connection_id)
        self.connection_user[connection_id] = user
        self.user_connections.setdefault(user, set()).add(connection_id)
        if (
            previous_user is not None
            and previous_user != user
            and not self.user_connections.get(previous_user)
        ):
            self.remove_user(previous_user)
        if user not in self.user_worker_map:
            self.assign_user(user, worker)

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

    def discard_page_edge(self, connection_id: str, page_id: str) -> None:
        """Take one page off its connection's edge set, dropping the set when empty.

        Called only for a connection just read off ``page_connection``, so the
        edge set exists by the alignment invariant — a missing one is a broken
        surface and raises (``KeyError``), never passes silently.
        """
        siblings = self.connection_pages[connection_id]
        siblings.discard(page_id)
        if not siblings:
            del self.connection_pages[connection_id]

    def drop_page(self, page_id: str, worker: str) -> None:
        """Unhang a page, unless it has meanwhile been placed somewhere else.

        Its subscriptions go with it: a page that exists nowhere subscribes to
        nothing, and a stale entry would make every commit on that table resolve
        a destination for a page nobody holds.
        """
        if self.page_worker(page_id) != worker:
            return
        self.forget_page_row(page_id)

    def forget_page_row(self, page_id: str) -> None:
        """Take one page row off the surface: its edge, its subscriptions.

        The unguarded half of ``drop_page``, for the caller that already OWNS
        the judgement — the fold checks the announcing worker first, the login
        rehome discards a remnant it snapshotted itself.
        """
        connection = self.page_connection.pop(page_id)
        self.discard_page_edge(connection, page_id)
        self.page_subscriptions.drop_page(page_id)

    def page_worker(self, page_id: str) -> str | None:
        """The worker holding a page, DERIVED: page → connection → user → worker.

        ``None`` at any missing hop, which is the whole of the old semantics — a
        page the surface does not know, a connection or user already swept —
        held by derivation instead of by a written flag somebody has to keep
        in step.
        """
        connection = self.page_connection.get(page_id)
        if connection is None:
            return None
        user = self.connection_user.get(connection)
        if user is None:
            return None
        return self.user_worker_map.get(user)

    def pages_of_connection(self, connection_id: str) -> list[str]:
        """Every page opened by one connection, sorted — the edge set read downward."""
        return sorted(self.connection_pages.get(connection_id, set()))

    def drop_user(self, user: str, worker: str) -> None:
        """Unmap a user, unless it has meanwhile been assigned somewhere else."""
        if self.user_worker_map.get(user) != worker:
            return
        self.remove_user(user)

    def assign_user(self, user: str, worker: str) -> None:
        """Point a user at a worker — the explicit decision, above the owner check.

        One of the two mutators of the surface: the user's half-row travels with
        it, so a re-pointing keeps the pending calls and the activity it already
        had. A user seen for the first time gets a fresh half-row.

        Every decision calls this the moment it is taken: the login's fold
        stamps the announcing worker here, and the move's switch stamps the
        destination once the install answered.

        The user's connections and pages travel with it and NOTHING is written
        for them: they answer the new worker the moment this map entry changes,
        because that is where their answer is derived from.

        A user coming back from the freezer has ``FROZEN`` as its previous
        placement — a state, not a worker — so there is no half-row to carry
        over: it was dropped when the parcel went to disk, and the wake gets a
        fresh one.
        """
        previous = self.user_worker_map.get(user)
        carried = None
        if previous is not None and previous not in (worker, FROZEN):
            carried = self.worker_roster[previous]["users"].pop(user, None)
        users = self.worker_roster[worker]["users"]
        if user not in users:
            users[user] = self.new_user_row() if carried is None else carried
        self.user_worker_map[user] = worker

    def remove_user(self, user: str) -> None:
        """Drop a user from the surface: its half-row and its map entry, together.

        The other mutator. The demolition follows the chain downward — every
        connection of the user, every page of each connection, and the
        connection entries after them: a page without its user exists nowhere,
        and neither does a connection.

        A ``FROZEN`` placement holds no half-row anywhere — the parcel took the
        slice off its worker — so only the map entry and the rows below it go.
        The parcel file stays for the reaper: nothing here reads it any more.
        """
        worker = self.user_worker_map.pop(user, None)
        if worker is not None and worker != FROZEN:
            del self.worker_roster[worker]["users"][user]
        self.forget_users([user])
        for connection_id in sorted(self.user_connections.pop(user, set())):
            for page_id in sorted(self.connection_pages.pop(connection_id, set())):
                del self.page_connection[page_id]
                self.page_subscriptions.drop_page(page_id)
            del self.connection_user[connection_id]

    def sweep_worker(self, worker: str) -> list[str]:
        """Forget every user of a dead worker: what they pointed at is gone.

        This reaches a user mid-move too — the map names the source until the
        switch — and the move machinery is built for exactly that window: a
        user gone from the surface makes the move answer False, and a parcel
        already in custody is salvaged onto a living worker regardless.
        """
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

        Every ``METRICS_WINDOW``-th reading also closes a floor: the window is
        by then a full one, and its lowest live memory — the evaluator's
        ``window_floor`` — is appended to the row's long ``floors`` series
        (issue #8). A window carrying no ``rss`` at all yields no floor and the
        counter simply restarts.
        """
        row = self.worker_roster[worker]
        window = row["occupancy"]
        counters = self.forward_counters.get(worker) or {
            "requests": 0,
            "errors": 0,
            "seconds": 0.0,
        }
        window.append({"ts": time.time(), "report": report, "forward": dict(counters)})
        row["floor_readings"] += 1
        if row["floor_readings"] >= METRICS_WINDOW:
            row["floor_readings"] = 0
            floor = self.evaluator.window_floor(worker)
            if floor is not None:
                row["floors"].append({"ts": time.time(), "floor": floor})

    def worker_floors(self, worker: str) -> deque[dict[str, Any]] | None:
        """The archived live-memory floor series of one worker, None when unknown.

        Twin of ``worker_window`` on the long axis: one ``{ts, floor}`` row per
        sampled window, oldest first. A known worker that has not closed a
        window yet reads as an empty deque.
        """
        return self.worker_roster.get(worker, {}).get("floors")

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
        ``floor`` is the last sampled live-memory floor in raw bytes and
        ``time_to_limit`` is ``worker_time_to_limit`` in hours rounded to one
        decimal — both None when the series is empty or the horizon is
        infinite (issue #8). Every number here is the evaluator's: nothing is
        judged.
        """
        view: dict[str, dict[str, Any]] = {}
        for name in self.active_workers:
            components = self.evaluator.worker_components(name)
            floors = self.worker_floors(name)
            time_to_limit = self.evaluator.worker_time_to_limit(name)
            view[name] = {
                "occupancy": round(self.evaluator.worker_saturation(name) * 100),
                "components": {key: round(value * 100) for key, value in components.items()},
                "history": [round(value * 100) for value in self.evaluator.worker_history(name)],
                "rates": self.evaluator.worker_rates(name),
                "floor": floors[-1]["floor"] if floors else None,
                "time_to_limit": round(time_to_limit, 1) if time_to_limit is not None else None,
                # a copy, like the archived snapshot: the view is the consumer's
                # to annotate, the ledger is not
                "forward": dict(
                    self.forward_counters.get(name)
                    or {"requests": 0, "errors": 0, "seconds": 0.0}
                ),
            }
        return view

    @property
    def pool_occupancy(self) -> dict[str, Any]:
        """The whole pool as the planner reads it: one picture, taken once.

        Takes nothing, modifies nothing. Returns ``{capacity, load, headroom,
        workers}``: the ledger totals in QUANTITY (``capacity_headroom`` is the
        authority — ``capacity`` is derived from it, so the two can never drift)
        plus one row per ACTIVE worker, keyed by name, carrying ``status``,
        ``saturation`` (the gate), ``load`` (the quantity), ``memory_pressure``
        — the last archived live-memory floor over the necessity budget
        ``memory_limit_mb * floor_limit_ratio``, 0.0 with no limit configured or
        no floor closed yet — and ``idle_users``: every held user with nothing
        pending, mapped to its idle age in seconds. An empty pool reads
        ``{0.0, 0.0, 0.0, {}}``.
        """
        now = time.time()
        budget = (self.memory_limit_mb or 0) * 1024 * 1024 * self.floor_limit_ratio
        workers: dict[str, Any] = {}
        for name in self.active_workers:
            row = self.worker_roster[name]
            floors = self.worker_floors(name)
            workers[name] = {
                "status": row["status"],
                "saturation": self.evaluator.worker_saturation(name),
                "load": self.evaluator.worker_load(name),
                "memory_pressure": (floors[-1]["floor"] / budget) if (floors and budget) else 0.0,
                "idle_users": {
                    user: now - entry["last_activity_ts"]
                    for user, entry in row["users"].items()
                    if not entry["pending"]
                },
            }
        load = sum(entry["load"] for entry in workers.values())
        headroom = self.capacity_headroom()
        return {
            "capacity": load + headroom if workers else 0.0,
            "load": load,
            "headroom": headroom,
            "workers": workers,
        }

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
        once logged, the session id while anonymous. A user a move is carrying
        is waited for first, so the pick lands on the worker the surface
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
        BEFORE the REPLY fold (the legacy order): the fold's own work (settling
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

        One hold, read BEFORE the pick: a move carrying this identity makes the
        map's answer provisional. The loop re-reads on every wakeup — a move
        that lands may be followed by another one raised for the same user —
        and with nothing up at the start it awaits nothing at all.

        This is also where a frozen user comes back: the placement says
        ``FROZEN``, the wake installs the parcel on a living worker and the pick
        below finds it there. The wake raises its own hold synchronously, so a
        second request arriving in the same instant parks on it instead of
        installing the parcel twice. A wake that answers False — the parcel
        expired while the placement still said ``FROZEN`` — has cleared that
        placement, so the pick below seats the user as the stranger it now is
        instead of failing every request it will ever make.
        """
        while self.is_held(identity):
            await self.await_move(identity)
        if self.user_worker_map.get(identity) == FROZEN:
            await self.unfreeze_user(identity)
        return self.worker_for(identity)

    def is_held(self, identity: str) -> bool:
        """Whether the one hold there is — a move of this identity — is up."""
        return identity in self.moving

    def worker_for(self, identity: str) -> str:
        """The worker holding ``identity`` — the reception when nobody does.

        A miss is a guest (or a user whose worker died): it goes to the reception,
        which is also the moment to check whether the pool still has room for one.

        WHO IS TURNED AWAY IS DECIDED BY THE POOL'S STATE, not by the request.
        While ``pool_status`` is ``restricted`` — a plan aborted because no fresh
        worker would register — a STRANGER is refused with a 503 and a
        ``Retry-After`` of one decision interval, which is when the pool will
        have decided again. A stranger is whoever the pool holds nothing of:
        neither a placement nor a parcel in the freezer. Everybody already
        inside is served exactly as ever, hibernated users included.

        With no reception at all there is nowhere to send anyone: at ``ready``
        that is an impossible state and says so with a RuntimeError, since a
        pool that answers requests always has a worker; ``restricted`` is the
        one condition in which it is expected, and it is the same 503.

        An ``evacuating`` or ``retiring`` worker still serves whoever is still on
        it: it holds their slices until the plan carries them over, and sending
        them to the reception instead would serve them where their state is not.

        A ``FROZEN`` placement never reaches here: ``resolve_worker`` wakes the
        user before it asks. Reaching it anyway is a broken caller and says so
        — the alternative, sending a frozen user to the reception, would serve
        it as a guest while its whole slice waits in a file.
        """
        if identity in self.user_worker_map:
            worker = self.user_worker_map[identity]
            if worker == FROZEN:
                raise RuntimeError(f"{identity} is frozen: wake it before routing it")
            if self.worker_roster[worker]["status"] in ("active", "evacuating", "retiring"):
                return worker
        reception = self.reception
        if self.pool_status == "restricted":
            stranger = identity not in self.user_worker_map and not (
                self.frozen_users_dir is not None
                and self.frozen_users_dir.child(self.user_to_userkey(identity)).exists()
            )
            if stranger or reception is None:
                # One of the two declared emitters of the anomaly channel (issue #19):
                # a pool that turned somebody away is a fact the sysop must see.
                # Retry-After is one decision interval: when the pool will have
                # re-read itself and decided again, so nobody has to guess.
                retry_after = str(int(self.decision_interval)).encode()
                raise HTTPException(503, "server busy", [(b"retry-after", retry_after)])
        if reception is None:
            raise RuntimeError("no worker available to serve the request")
        self.check_capacity()
        return reception

    def decide_worker(self) -> str:
        """Where a just-logged user BELONGS: reception-first.

        Asked by ``settle_login`` for a first login only — a resident's
        presence answers before occupancy is ever consulted. The user already
        LIVES where it logged in; this names where it belongs, and a different
        answer becomes a detached move. The reception KEEPS the login while it
        stays under ``reception_threshold`` (and a sole worker keeps always);
        over the threshold it PASSES to the least loaded of the others that
        still admit. The admission gate never blocks a login: with every other
        worker over it the last one takes the user anyway, under a warning, and
        growth is ``check_capacity``'s business. That check runs AFTER the
        pick, so a login never lands on the worker its own arrival spawned.
        """
        candidates = self.active_workers
        if not candidates:
            raise RuntimeError("no worker available to place a login")
        chosen = self.pick_placement(candidates)
        self.check_capacity()
        return chosen

    def pick_placement(self, candidates: list[str]) -> str:
        """The reception-first pick over ``candidates`` (the active workers).

        A ``retiring`` worker is out of the choice: a plan in flight is taking it
        away, and a login seated there would be moved again within the tick. The
        reception is the one exception the pool cannot afford — with every other
        worker retiring it still takes the login, because a placement always
        answers.
        """
        reception = candidates[0]
        others = [
            name for name in candidates[1:] if self.worker_roster[name]["status"] != "retiring"
        ]
        under_threshold = (
            self.evaluator.worker_saturation(reception) < self.reception_threshold
            and self.worker_roster[reception]["status"] != "retiring"
        )
        if not others or under_threshold:
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

        A ``retiring`` worker does not count as room: it is on its way out, so a
        pool whose only spare capacity sits on one still has to widen.
        """
        active = self.active_workers
        if not active:
            return
        reception = active[0]
        others = [name for name in active[1:] if self.worker_roster[name]["status"] != "retiring"]
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

        Two things ride the closing of a user's LAST live call:

        - the bookkeeping of an identity that is on no map (a guest, a call
          that never became a login) lives only as long as its calls — the row
          is dropped here, and the next call recreates it for its own duration.
          Anonymous traffic leaves no standing note on the orchestrator, which
          is the legacy dispatcher's own rule;
        - a user resident on an EVACUATING worker is carried over NOW: the
          instant between a response and the next request is the one moment a
          busy user is certainly free, so the move launches here instead of
          hoping a clock ever finds him idle.
        """
        row = self.worker_roster[worker]
        entry = row["users"].get(user)
        if entry is None:
            return
        entry["pending"].pop(request_id, None)
        if entry["pending"]:
            return
        if self.user_worker_map.get(user) != worker:
            del row["users"][user]
            return
        if row["status"] == "evacuating":
            self.spawn_pool_pass(self.evacuate_user(user, worker))

    async def evacuate_user(self, user: str, worker: str) -> None:
        """Carry one just-freed user off its evacuating worker — the call-close move.

        Failure is the one genuinely anomalous situation of the story (in
        normal conditions an idle user packs and travels): the user gets an
        ERROR, not a silent limbo — the surface FORGETS him, so his next call
        is a loud KeyError on a worker that never knew his pages, the client
        re-logins and is seated fresh on a healthy worker. The untransportable
        slice stays orphaned on the sick worker and dies with its clocks. The
        event is reported for a human (the server's anomaly channel when it
        exists; this ERROR log meanwhile).
        """
        target = self.pick_compaction_target(worker)
        try:
            moved = target is not None and await self.move_user(user, target)
        except Exception as exc:
            self.logger.warning(
                "Evacuation move of %s failed (%s: %s)", user, type(exc).__name__, exc
            )
            moved = False
        if moved:
            return
        if self.user_worker_map.get(user) != worker:
            return
        self.logger.error(
            "Evacuation of %s cannot carry %s: session dropped, the user must log in "
            "again (anomaly to report on the server channel)",
            worker,
            user,
        )
        self.remove_user(user)

    # ------------------------------------------------------------------
    # The login settle: the fold stamps the map, a detached task moves what
    # belongs elsewhere (ratified 2026-08-12 — the login never ships)
    # ------------------------------------------------------------------

    def place_logins(self, worker: str, events: list[dict[str, Any]]) -> None:
        """Fold this REPLY's events and settle each login they carry.

        Applied in delivered order, no dedup and no ordering gate: the envelope
        is causal and delivered once, so every event in it is fresh — the
        legacy removed its own seq counters for the same reason (they rejected
        legitimate post-move events). The owner check inside ``fold_event`` is
        the only guard.

        A login is settled right here, on the caller's own tick, and the
        settling is a DECISION, never a wait: the fold has already mapped a
        first-login user to the worker that announced it, and what the decision
        orders — a move toward the worker the user belongs on, the discard of a
        remnant left behind by a login onto a user resident elsewhere — leaves
        as a DETACHED task. The caller is released with the response; the
        move's own ``moving`` hold parks whatever arrives for that user in the
        meantime. ``prior`` — where the map pointed BEFORE the login folded —
        is read on the same tick, because the fold itself is what changes it.
        """
        for event in events:
            is_login = event.get("op") == LOGIN_OP
            prior = self.user_worker_map.get(event["user"]) if is_login else None
            self.fold_event(worker, event)
            if is_login:
                self.settle_login(worker, event["user"], event["connection_id"], prior)

    def settle_login(self, worker: str, user: str, connection_id: str, prior: str | None) -> None:
        """One login's decision, taken synchronously on the fold's own tick.

        A ``FROZEN`` PLACEMENT answers before ``prior`` is even consulted: the
        user has a slice waiting on disk, so the login is a WAKE and it carries
        the file to the worker the connection is already open on — ``add_user``
        joins the parcel to the rows the login just made there. The question is
        asked of the MAP and not of the disk, so a parcel nobody is placed on
        any more — an orphan the reaper has not reached — can never be
        delivered over a user who is alive and logging in.

        Three shapes otherwise, told apart by ``prior``:

        - nobody held the user: the fold just mapped it to ``worker``, where it
          logged in. ``decide_worker`` — the same reception-first policy as
          ever — says whether it BELONGS elsewhere; if so, the ordinary
          commanded move carries it, detached.
        - the user was resident on this very worker: the worker's join was the
          whole login and the fold moved the connection edge. Nothing to do.
        - the user was resident on ANOTHER worker: not a move — the arriving
          connection belongs at the residence, and what the guest accumulated
          on ``worker`` dies with the remnant (the resident wins, the declared
          boundary). The remnant's page rows are snapshotted HERE, on the
          fold's tick, so the detached task never confuses them with pages
          born at the residence afterwards.

        The wake's per-user barrier is raised HERE, synchronously, before the
        task detaches: a request arriving in the window between this tick and
        the task's first step would otherwise find a ``FROZEN`` placement with
        no hold up and install the same parcel a second time. The detached wake
        inherits the hold and releases it in its own ``finally`` — the guarantee
        ``resolve_worker`` documents, extended to the one path that lacked it.

        A hold ALREADY up for a user the map reads ``FROZEN`` means a wake of
        that user is in flight — the near-impossible case, since the cookie
        state that produces a login and the one that produces a request are
        exclusive. The login does not touch that hold and spawns no wake: one
        owner per Event, never a shared hold. It is logged as a WARNING and
        left alone, because it is self-healing — the wake in flight lands the
        user on a worker and the NEXT login of that session reconciles the
        connection through ``rehome_login``, the ordinary path for a login that
        arrives away from the residence.

        One race is ACCEPTED (probability-weighted rule, 2026-08-12): a second
        guest logging in as the SAME user inside the evict-to-switch window of
        that user's login move re-keys onto the source and settles as "at
        home" — a ghost slice the switch then strands there. The window is
        milliseconds inside an already rare event; the outcome is loud — a
        KeyError on the ghost's next call, a reload — and the expiry sweep
        retires the leftovers. No machinery covers it.
        """
        if self.user_worker_map.get(user) == FROZEN:
            if user in self.moving:
                self.logger.warning(
                    "login of %s found a hold already up; leaving the wake to the next request",
                    user,
                )
            else:
                self.moving[user] = asyncio.Event()
                self.spawn_settlement(self.unfreeze_user(user, worker), name=f"login-wake:{user}")
        elif prior is None:
            chosen = self.decide_worker()
            if chosen != worker:
                self.spawn_settlement(self.move_user(user, chosen), name=f"login-move:{user}")
        elif prior != worker:
            remnant_pages = self.pages_of_connection(connection_id)
            self.spawn_settlement(
                self.rehome_login(worker, user, connection_id, remnant_pages),
                name=f"login-rehome:{user}",
            )

    def spawn_settlement(self, coro: Coroutine[Any, Any, Any], name: str) -> asyncio.Task[Any]:
        """Run one login settlement on its own task, holding a strong ref.

        Same discipline as the task-class commands: nobody awaits it, the set
        keeps it alive, and ``log_task_error`` leaves a line if it dies.
        """
        task = asyncio.create_task(coro, name=name)
        self._command_tasks.add(task)
        task.add_done_callback(self._command_tasks.discard)
        task.add_done_callback(self.log_task_error)
        return task

    async def rehome_login(
        self, source: str, user: str, connection_id: str, remnant_pages: list[str]
    ) -> None:
        """Settle a login onto a user resident elsewhere: discard, then join.

        The remnant at ``source`` — the guest entry the login re-keyed, its
        connection row, its pages — is discarded first: the map never named
        ``source``, so nothing routes there, and a slice nobody points at
        would otherwise linger invisibly. The parcel the evict answers with is
        DROPPED: the resident wins, and what the guest did before logging in
        dies with the remnant, loudly logged, never silently kept. The
        surface page rows follow, from the snapshot taken on the fold's tick.
        Then the arriving connection is materialized at the residence, so the
        worker's registers and this surface tell the same story; its events
        ride that CALL's REPLY and fold as any other.

        A move of this user in flight is waited out first and the residence
        re-read after it — the map is the authority at every step. A residence
        that meanwhile became ``source`` itself means the slices already
        joined there: nothing to discard. A user gone from the surface means
        the sweeps got there first: only the remnant is cleaned.
        """
        await self.await_move(user)
        residence = self.user_worker_map.get(user)
        if residence == source:
            return
        try:
            await self.evict_for_move(user, source)
            self.logger.info(
                "Login of %s on %s: remnant discarded, the resident on %s wins",
                user,
                source,
                residence,
            )
        except Exception as exc:
            self.logger.warning(
                "Login of %s on %s: remnant eviction failed (%s: %s)",
                user,
                source,
                type(exc).__name__,
                exc,
            )
        # The rows go even when the evict failed: every way it can fail — the
        # source died, the remnant already expired — means those pages are gone
        # regardless. A row a drop_page folded away meanwhile is skipped.
        for page_id in remnant_pages:
            if page_id in self.page_connection:
                self.forget_page_row(page_id)
        # The map is the authority at every step: the evict was an await, so a
        # move raised meanwhile is waited out and the residence is read AGAIN
        # before the connection is materialized — the row must never land on a
        # worker the user has just left.
        await self.await_move(user)
        residence = self.user_worker_map.get(user)
        if residence is None or residence == source:
            return
        path = f"{OP_PATH_PREFIX}new_connection"
        payload = await self.hub.call(
            residence, path, {"identity": connection_id, "kwargs": {"user": user}}
        )
        await self.unwrap_reply(residence, path, payload)

    # ------------------------------------------------------------------
    # The commander-initiated move: flag, quiesce, custody, switch
    # ------------------------------------------------------------------

    async def move_user(self, user: str, target: str) -> bool:
        """Carry one user's whole slice from where it lives to ``target``.

        FLAG → QUIESCE → evict → install → SWITCH. The flag is a barrier under
        the user's key: every forward of it parks before the pick, so nobody is
        routed at a worker the slice is leaving. The map keeps pointing at the
        SOURCE until the switch. Since the login stopped shipping (2026-08-12)
        this hold is the only one there is — the login's own settle rides this
        very machinery when the user belongs elsewhere.

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

        A user that left the surface while this move was parked — its landing
        failed, its worker died — is nobody's move any more: False, not an
        error, because the drains reach exactly this window by design.
        """
        source = self.user_worker_map.get(user)
        if source is None:
            self.logger.warning("Move of %s skipped: it left the surface first", user)
            return False
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
            if user not in self.user_worker_map:
                # The sweep took the user while the parcel was in custody: the
                # source died and the surface rows are gone. Re-writing the map
                # over a demolished surface would leave a half-resurrected user
                # whose page deliveries silently vanish — so the slice is
                # discarded where it landed, loudly, and the user is exactly as
                # dead as if no move had been in flight.
                self.logger.warning(
                    "Move of %s: swept mid-move (its source died), slice discarded on %s",
                    user,
                    destination,
                )
                try:
                    await self.evict_for_move(user, destination)
                except Exception as exc:
                    self.logger.warning(
                        "Move of %s: discard on %s failed too (%s: %s)",
                        user,
                        destination,
                        type(exc).__name__,
                        exc,
                    )
                return False
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

    async def hand_user_to(
        self, worker: str, user: str, encoded: str, parcel_wins: bool = False
    ) -> Any:
        """Deliver one user's encoded slice to ``worker`` and await its answer.

        ``parcel_wins`` decides who is the truth if the destination already has
        this user: normally the RESIDENT is, and the parcel joins it. The wake
        of a hibernated user is the one exception — see ``unfreeze_user`` — and it
        passes True, so the carried store takes the resident's place.

        The single door of the ``add_user`` handover — the move's custody and
        the dump restore both pass through here. One delivery at a time per
        destination: the worker's REMOVALIST (its lock in ``removalists``)
        queues the deliveries, so ``pending_users`` holds at most one entry
        per worker BY CONSTRUCTION and the caretaker's second eye reads an
        exact clock — the entry is written when the CALL actually leaves
        (time spent queueing is never "sitting on a delivery") and falls with
        the answer, whatever the answer is. The serving guard is read AFTER
        the queue, so a delivery that waited its turn sees the destination's
        CURRENT status, not the one it entered the queue with.
        """
        async with self.removalists.setdefault(worker, asyncio.Lock()):
            entry = self.worker_roster.get(worker)
            if entry is None or entry["status"] not in ("active", "evacuating", "retiring"):
                # The rare landing race, ACCEPTED (probability-weighted rule,
                # 2026-08-12): a delivery decided an instant before its target
                # stopped serving fails HERE, loudly — the caller errors, the
                # client retries, and by then the surface names a living worker.
                # No machinery covers the window; what is forbidden is landing a
                # slice on a worker under SIGTERM and telling the client "done".
                raise RuntimeError(f"worker {worker!r} is not serving: cannot deliver {user}")
            path = f"{OP_PATH_PREFIX}add_user"
            self.pending_users[worker] = time.time()
            try:
                payload = await self.hub.call(
                    worker,
                    path,
                    {
                        "identity": user,
                        "kwargs": {"encoded": encoded, "parcel_wins": parcel_wins},
                    },
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
                answer = await self.hand_user_to(destination, user, encoded)
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
                if isinstance(answer, dict) and answer.get("joined"):
                    # The accepted race, made loud: a commanded move never
                    # expects a resident at its destination — a join there
                    # means a login re-keyed onto it first and the parcel's
                    # own entry and store yielded to the earlier arrival.
                    self.logger.warning(
                        "Install of %s on %s JOINED a resident: the parcel's entry "
                        "and store yielded to whoever got there first",
                        user,
                        destination,
                    )
                return destination
        raise RuntimeError(f"move of {user} lost its room: no worker left to install it on")

    def salvage_target(self, tried: set[str]) -> str | None:
        """The least loaded active worker no install of this move has burned yet.

        A ``retiring`` worker is never a salvage landing: a plan in flight has
        already named it, so the rescued user would only be moved again by the
        very next step.
        """
        candidates = [
            name
            for name in self.active_workers
            if name not in tried and self.worker_roster[name]["status"] != "retiring"
        ]
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
        the registry is re-read on every wakeup.
        """
        while True:
            barrier = self.moving.get(identity)
            if barrier is None:
                return
            await barrier.wait()

    # ------------------------------------------------------------------
    # The freezer: an idle user hibernates to a file, and wakes from it
    # ------------------------------------------------------------------

    @property
    def freeze_candidates(self) -> list[tuple[str, str]]:
        """The ``(user, worker)`` pairs due for the freezer, longest idle first.

        Takes nothing, modifies nothing. Empty while the freezer is disarmed
        (``freeze_idle_after`` is None). A user is due once its idle age passes
        the EFFECTIVE idle of the worker holding it: ``freeze_idle_after``
        shortened in proportion to that worker's memory pressure and never
        brought under ``freeze_idle_floor`` — the fuller the memory, the sooner
        an idle user goes to disk. Read off the ONE ``pool_occupancy`` picture,
        whose ``idle_users`` already leaves out everybody with work in flight:
        a user mid-call is never a candidate.
        """
        if self.freeze_idle_after is None:
            return []
        due: list[tuple[float, str, str]] = []
        for worker, row in self.pool_occupancy["workers"].items():
            effective = max(
                self.freeze_idle_after * (1.0 - row["memory_pressure"]), self.freeze_idle_floor
            )
            for user, idle_age in row["idle_users"].items():
                if idle_age <= effective:
                    continue
                due.append((idle_age, user, worker))
        due.sort(reverse=True)
        return [(user, worker) for _, user, worker in due]

    def user_to_userkey(self, user: str) -> str:
        """The filename every file of ``user`` goes by: its identity, percent-encoded.

        ONE WAY by design: every reader starts from the user and computes the
        key forward — nothing ever derives a user back from a filename (the
        reaper walks the placements it already knows; orphan files die by age
        alone). ``quote`` with nothing declared safe keeps every separator out
        of the name, so no identity can step outside the directory it is filed
        under, and ``GUEST_PREFIX`` comes through untouched, so the class is
        still read off the file itself. A bare ``.`` or ``..`` survives quoting
        and fails LOUDLY at the write — it names a directory — the accepted end
        of an identity no login mints.
        """
        return urllib.parse.quote(user, safe="")

    async def freeze_user(self, user: str) -> bool:
        """Park one user's whole slice in a file and mark its placement ``FROZEN``.

        QUIESCE → seal → file → placement: the freezer's half of the move
        machinery, and it raises the SAME per-user barrier, so every forward of
        this user parks while the slice leaves. The worker seals and spends its
        copy answering (off its loop, see ``UserStickyWorker.freeze_user``), and
        the commander writes the parcel under ``frozen_users_dir /
        user_to_userkey(user)``, DIRECTLY: a parcel is 2–45 KB, and the half-write window a temp file
        would retire is narrower than the cost of the discipline. A truncated
        parcel is not silent — it fails to unpickle at the wake, which treats
        it exactly as an expired one.

        The rows below the user STAY: a frozen user still owns its connections
        and its pages, and they answer a worker again the moment ``unfreeze_user``
        re-points the map. What goes is its half-row on the worker — there is no
        worker holding it any more.

        Returns whether the user actually went to disk. A user nobody holds, one
        already frozen, one whose calls do not drain inside the quiesce budget,
        and one whose worker died mid-seal all stay exactly as they were.

        Everything that can be asked before the seal is asked there: past the
        seal the slice exists nowhere but in this call. The directory is made
        before it; whether it takes writes at all is a question a storage node
        cannot answer in advance, so a freezer pointed at somewhere unwritable
        is discovered AT the write and takes the loud road below.

        A disk that fills BETWEEN that question and the write is an operations
        concern, not this code's: the write is logged as an ERROR naming the
        user and the directory, and the user is dropped from the surface so
        that its next contact restarts it cleanly as a stranger instead of
        spamming KeyErrors against a worker that has already let the slice go.
        """
        worker = self.user_worker_map.get(user)
        if worker is None or worker == FROZEN:
            return False
        if self.frozen_users_dir is None:
            raise ValueError(f"freeze of {user}: the freezer has no directory to write to")
        if user in self.moving:
            raise RuntimeError(f"move of {user} is already in flight")
        self.moving[user] = asyncio.Event()
        try:
            self.frozen_users_dir.mkdir(parents=True, exist_ok=True)
            if not await self.quiesce_user(user, worker):
                self.logger.warning(
                    "Freeze of %s skipped: its calls did not drain in %ss",
                    user,
                    self.move_quiesce_timeout,
                )
                return False
            path = f"{OP_PATH_PREFIX}freeze_user"
            try:
                payload = await self.hub.call(worker, path, {"identity": user, "kwargs": {}})
                encoded = str((await self.unwrap_reply(worker, path, payload))["encoded"])
            except Exception as exc:
                self.logger.warning(
                    "Freeze of %s on %s aborted (%s: %s)", user, worker, type(exc).__name__, exc
                )
                return False
            if self.user_worker_map.get(user) != worker:
                # The same window ``move_user`` documents: the sweep took the
                # user while its parcel was on the wire. Writing the file now
                # would park a slice whose surface rows are already demolished,
                # so it is dropped and the user is as gone as it already is.
                self.logger.warning(
                    "Freeze of %s: swept mid-seal (its worker died), parcel discarded", user
                )
                return False
            parcel = self.frozen_users_dir.child(self.user_to_userkey(user))
            try:
                parcel.write_text(encoded)
            except Exception as exc:
                self.logger.error(
                    "Freeze of %s: the parcel could not be written to %s (%s: %s); "
                    "the user is dropped and comes back as a stranger",
                    user,
                    self.frozen_users_dir,
                    type(exc).__name__,
                    exc,
                )
                self.remove_user(user)
                return False
            del self.worker_roster[worker]["users"][user]
            self.user_worker_map[user] = FROZEN
            self.logger.info("Froze %s off %s into %s", user, worker, parcel)
            return True
        finally:
            self.release_move(user)

    async def unfreeze_user(self, user: str, worker: str | None = None) -> bool:
        """Bring a frozen user back out of its file, onto a living worker.

        The install goes through the ORDINARY placement — ``decide_worker``,
        the same reception-first policy a login gets — unless ``worker`` names
        one: a login carries its own destination, because the connection that
        woke the user is already open there. Either way the parcel travels the
        ordinary handover, so a worker that cannot take it fails this wake
        loudly instead of half-installing.

        **On a wake the PARCEL is the truth** (declared exception to the
        ``add_user`` JOIN, this path only). A frozen user by definition had no
        live entry anywhere, so an entry found at the destination was made
        minutes ago by the login's own re-key, against days of hibernated
        state: the delivery goes out with ``parcel_wins``, the carried store
        takes the resident's place with every watching page re-attached to it,
        and the override is logged. Every other path — logins, moves — keeps
        the ratified JOIN, where the resident wins.

        The surface is relearned from the parcel, exactly as ``restore_dump``
        relearns it: an operational install shapes no event, so a commander that
        has forgotten this user — restarted since the hibernation — would hold
        its placement and none of the connections, pages and table
        subscriptions under it. ``adopt_slice`` re-hangs them with the lifecycle
        mutators, which re-state what a same-process wake already knows rather
        than duplicating it.

        The file is DELETED once the install has answered: the parcel is spent,
        and a spent parcel is nobody's.

        Returns whether the user came back — asked by TRYING: the parcel is
        read, never asked about first. A parcel that is missing has EXPIRED —
        the reaper outlived its class, or the file went by hand — one that
        will not unpickle is truncated, and a freezer disarmed since the
        placement froze holds nothing at all. None of these is an impossible
        state: the placement and the rows under it are cleared (``remove_user``
        already handles a ``FROZEN`` row), the answer is False, and
        ``resolve_worker`` falls through to ``worker_for`` so the user restarts
        as a stranger. A permanent 500 on every future request is the
        alternative this refuses.

        The per-user barrier may already be up when this is called: the login
        path raises it synchronously in ``settle_login`` and hands it over, so a
        hold found here is this wake's own and is adopted rather than refused.
        No other hold can be up — a FROZEN placement is on no roster, so no move
        of this user can be in flight.
        """
        if self.frozen_users_dir is None:
            self.logger.warning("wake of %s: the freezer is disarmed; treating as new", user)
            if self.user_worker_map.get(user) == FROZEN:
                self.remove_user(user)
            if user in self.moving:
                self.release_move(user)
            return False
        if user not in self.moving:
            self.moving[user] = asyncio.Event()
        try:
            parcel = self.frozen_users_dir.child(self.user_to_userkey(user))
            try:
                encoded = parcel.read_text()
                pickle.loads(base64.b64decode(encoded))
            except Exception as exc:
                self.logger.warning(
                    "frozen parcel of %s is missing or unreadable (%s: %s); treating as new",
                    user,
                    type(exc).__name__,
                    exc,
                )
                if parcel.exists():
                    parcel.delete()
                if self.user_worker_map.get(user) == FROZEN:
                    self.remove_user(user)
                return False
            destination = worker or self.decide_worker()
            answer = await self.hand_user_to(destination, user, encoded, parcel_wins=True)
            if isinstance(answer, dict) and answer.get("joined"):
                self.logger.warning(
                    "Wake of %s on %s found a resident entry: the hibernated store "
                    "overrode the one the login had just made",
                    user,
                    destination,
                )
            self.assign_user(user, destination)
            self.adopt_slice(user, destination, encoded)
            parcel.delete()
            self.logger.info("Woke %s onto %s", user, destination)
            return True
        finally:
            self.release_move(user)

    def reap_frozen_files(self) -> None:
        """Delete the parcels that have outlived their class. Nothing else.

        PURE housekeeping: it moves no user, touches no placement and reads no
        map — it only takes files off the disk. Nothing to do with the freezer
        disarmed or before the first parcel has been written.

        A parcel is kept until it outlives its class: ``FROZEN_GUEST_LIFETIME``
        for a guest — the name carries ``GUEST_PREFIX``, so the class is read
        off the file itself — ``FROZEN_USER_LIFETIME`` for a logged user. A
        spent parcel is not its business either: ``unfreeze_user`` deletes the file
        it installed.

        The ``FROZEN`` placement of a user whose parcel is reaped here is left
        exactly where it is, and that is deliberate: ``unfreeze_user`` already
        answers a missing parcel by clearing the placement and restarting the
        user as a stranger, so the expiry needs no second implementation on the
        housekeeping side.
        """
        if self.frozen_users_dir is None or not self.frozen_users_dir.exists():
            return
        now = time.time()
        for node in sorted(self.frozen_users_dir.children(), key=lambda c: c.basename):
            lifetime = (
                FROZEN_GUEST_LIFETIME
                if node.basename.startswith(GUEST_PREFIX)
                else FROZEN_USER_LIFETIME
            )
            if now - node.mtime() > lifetime:
                node.delete()
                self.logger.info(
                    "Reaped the expired parcel %s (over %ss old)", node.basename, lifetime
                )

    # ------------------------------------------------------------------
    # The planner: one PLAN per tick, built from one reading of the pool
    # ------------------------------------------------------------------

    async def planner(self) -> None:
        """Decide the pool's shape on its own slow clock, and run what it decides.

        The shape of a pool is not an emergency: it is read whole every
        ``decision_interval`` and never one move per probe return. The probes
        keep their 5s cadence for HEALTH alone, and the fast reflexes that end a
        dead worker — the caretaker's kill, ``channel_lost``, the reconcile's
        respawn — are untouched by this cadence.

        Each tick closes the books of the open evacuations first: retiring the
        emptied, reporting the stalled. That bookkeeping never waits on
        anything, and the moves themselves ride the users' own calls
        (``close_request``). The freezer's disk is swept in the same breath
        (``reap_frozen_files``): housekeeping is not a plan step, it moves nobody.

        Then the shape: ``build_plan`` answers with the ordered steps, or with
        nothing when a plan is already in flight. This task IS the executor —
        the plan is awaited here, so the next tick finds it finished. A tick
        that falls over leaves its line on the log and the clock keeps running:
        a pool whose shape stopped being decided at all would go unnoticed.
        """
        while True:
            await asyncio.sleep(self.decision_interval)
            try:
                self.advance_evacuations()
                self.reap_frozen_files()
                plan = self.build_plan()
                if plan:
                    await self.execute_plan(plan)
            except Exception:
                self.logger.exception("Planner tick failed")

    def build_plan(self) -> list[dict[str, Any]]:
        """The ordered steps ONE reading of the pool calls for, and the claim on them.

        THE LADDER, rung by rung, every one of them decided against the same
        instant — the build is one synchronous breath, so nothing re-reads a pool
        an earlier rung has changed:

        1. FREEZE. The idle go to disk first, because a user hibernated is a user
           nobody has to move: every rung above it reasons on a lighter pool.
        2. REBALANCE. A worker over its own threshold is somebody's latency RIGHT
           NOW, which is the only thing here that hurts a request in flight.
        3. REPLACE, worst first — the workers whose live-memory floor has reached
           its budget (NECESSITY), then the ones holding memory they are not
           using, most wasteful first (CONVENIENCE); a worker that is both is
           condemned once, as a necessity. A replacement spawns only when the
           rest of the pool cannot take its users with margin — a gate asked NET
           of the condemnations this same plan already absorbs, so the second
           one does not count the room the first is taking away — and condemning
           the reception always spawns (R3: role continuity, not capacity).
        4. SPAWN of spare. R5's "create" half, asked of the pool AS THIS PLAN
           WOULD LEAVE IT: net of the workers leaving without a successor, the
           condemnations the gate absorbs and the folds below. At most one — a
           pool one worker short of comfortable is widened once, and the next
           tick reads the result.
        5. COMPACT. Slack last: it only costs memory to leave alone.

        A ``restricted`` pool carries ONE probe spawn at the TAIL of the ladder
        whatever the ledger says: the restriction is lifted by positive proof
        that a fresh process can start, so the planner is its retry engine — a
        trigger that has since lapsed must not strand the latch. It goes last
        because a failed spawn aborts the plan: nothing below the probe depends
        on the widening (unlike the ladder's own rung 4, which the folds read
        after), so a probe that fails must not suppress the freeze, replace and
        compact rungs the ledger did ask for. The probe is the plan's only
        spawn: any step that already raises a process — the ladder's own spawn
        rung, or a replace carrying ``spawn`` — IS the proof the restriction is
        waiting for, and two children for one tick is a pool widened twice. It
        carries ``probe``, so the execute side can drop it once the restriction
        has meanwhile lifted, and it runs under the same guards as any spawn.

        The in-process worker of the single role is never condemned: it IS the
        commander's process, so no successor could shed its leak.

        Returning the steps also CLAIMS them: ``active_plan`` is set here, in the
        same synchronous breath as the reading, so two planner ticks landing in
        the same loop iteration cannot both build. A build while a
        plan is in flight returns no second plan.

        Every worker a step NAMES is stamped ``retiring`` in that same breath,
        and the condemnations stamp INSIDE their own loop: from the instant a
        worker is named it stops being a destination, so no later step of this
        plan sheds onto a worker an earlier one takes out, and no gate counts as
        a receiver a worker already condemned. ``release_plan`` un-stamps
        whatever the plan never actually took out. A freeze step names a USER,
        not a worker: it stamps nothing.
        """
        if self.active_plan is not None:
            return []
        steps: list[dict[str, Any]] = [
            {"op": "freeze", "user": user, "worker": worker}
            for user, worker in self.freeze_candidates
        ]
        if self.rebalance_excess():
            steps.append({"op": "rebalance"})
        reception = self.reception
        condemned = self.condemned_workers()
        leaving_workers: list[str] = []
        for worker in condemned:
            if worker == reception:
                spawn = True  # role continuity, never capacity
            else:
                occupancy, reserve = self.workers_occupancy_metric([worker, *leaving_workers])
                margin_left = (
                    self.capacity_headroom() + occupancy - reserve - self.compaction_margin
                )
                users_fit = all(
                    self.pick_best_fit(weight, exclude=worker) is not None
                    for weight in self.rebalance_weights(worker).values()
                )
                spawn = margin_left <= 0 or not users_fit
            steps.append({"op": "replace", "worker": worker, "spawn": spawn})
            self.worker_roster[worker]["status"] = "retiring"
            if not spawn:
                leaving_workers.append(worker)
        folding = self.compaction_order(condemned)
        # The pool as this plan would leave it: the load of the workers going
        # out comes back on the ledger, their reserve goes with them.
        occupancy, reserve = self.workers_occupancy_metric(leaving_workers + folding)
        if self.capacity_headroom() + occupancy - reserve < self.spawn_margin:
            if self.max_workers is not None and self.target >= self.max_workers:
                self.logger.warning(
                    "Pool full at max_workers=%s; the plan cannot spawn", self.max_workers
                )
            else:
                steps.append({"op": "spawn"})
        for worker in folding:
            steps.append({"op": "compact", "worker": worker})
            self.worker_roster[worker]["status"] = "retiring"
        if self.pool_status == "restricted" and not any(
            step["op"] == "spawn" or step.get("spawn") for step in steps
        ):
            steps.append({"op": "spawn", "probe": True})
        self.active_plan = steps or None
        return steps

    def release_plan(self) -> None:
        """Drop the claim on the plan and give back whoever it never took out.

        Clears ``active_plan`` and rolls every row still stamped ``retiring``
        back to ``active``. A step that RAN has already moved its worker on —
        ``evacuating`` for a replacement, ``draining`` for a fold — so what still
        reads ``retiring`` is exactly what was skipped or never reached, and it
        goes back to being a full member of the pool. Building and discarding a
        plan without releasing it is impossible by construction: this is the one
        door out.
        """
        self.active_plan = None
        for entry in self.worker_roster.values():
            if entry["status"] == "retiring":
                entry["status"] = "active"

    def condemned_workers(self) -> list[str]:
        """The workers this plan replaces, necessity first then convenience.

        The two triggers of R5 in the order the register puts them, each worker
        named once. The in-process worker is out: it cannot be succeeded.
        """
        in_process = self.worker.name if self.worker is not None else None
        condemned = []
        for worker in self.necessity_candidates() + self.convenience_candidates():
            if worker != in_process and worker not in condemned:
                condemned.append(worker)
        return condemned

    def compaction_order(self, condemned: Sequence[str] = ()) -> list[str]:
        """The workers this plan folds away, emptiest first, while the ledger allows it.

        Emptiest first is literal: the ones already holding no user come first —
        their fold costs no move at all — then the rest of the pool by ascending
        load, because the compaction is ACTIVE (R5) and takes the last users off
        the emptiest worker to free it.

        A worker this plan already CONDEMNS is not folded on top of that: its
        replacement step takes it out of the pool by itself, and a fold aimed at
        a row already on its way out would find nothing left to retire. The same
        goes for a row already stamped ``retiring`` — a fold this very build has
        just planned, or one an earlier plan has yet to run.

        A candidate is kept only while the headroom READ WITHOUT the folds
        already planned stays OVER ``compaction_margin`` — a margin means a
        margin, so a fold landing exactly on it is refused; the pool as it would
        stand once this plan has run, not as it reads now. Each fold costs a
        whole gate of capacity and gives back what its worker holds, which is the
        ledger's own arithmetic applied to a pool that is still hypothetical.
        The reception is never a candidate: it is the guests' worker, the one
        address a pool always has.
        """
        empty = [
            name
            for name in self.empty_workers()
            if name not in condemned and self.worker_roster[name]["status"] != "retiring"
        ]
        rest = sorted(
            (
                name
                for name in self.active_workers[1:]
                if name not in empty
                and name not in condemned
                and self.worker_roster[name]["status"] != "retiring"
            ),
            key=self.evaluator.worker_load,
        )
        headroom = self.capacity_headroom()
        folding = []
        for name in empty + rest:
            after = headroom - 1.0 + self.evaluator.worker_load(name)
            if after <= self.compaction_margin:
                break
            folding.append(name)
            headroom = after
        return folding

    async def execute_plan(self, plan: list[dict[str, Any]]) -> None:
        """Run the steps in order, one at a time, then release the claim.

        Sequential by construction: each step reads a pool the previous one has
        already changed, which is why they were ordered at build time and not
        dispatched together. A step that raises ends the whole plan — the next
        tick re-reads the world and decides again, which is the only retry there
        is. However it ends, the claim is dropped through ``release_plan``, which
        also hands back every worker this plan named and never took out.

        A compaction step re-reads the pool before it moves anybody: the plan was
        ordered against a pool the steps before it have since changed. A fold the
        ledger no longer authorizes is skipped rather than paid for, and so is one
        whose worker has meanwhile left the active pool or BECOME the reception —
        a replacement step ahead of it moves that role, and the reception is never
        folded away. The drain is what makes it ACTIVE — the last users leave, one
        whole ``move_user`` each — and a drain that does not empty its worker
        retires nothing.

        A freeze step is a whole ``freeze_user`` round trip, and a user that has
        meanwhile moved, gone or come back to life simply does not go to disk:
        the freezer answers False and the plan carries on. A spawn step raises the
        target first — the reconcile must not read the new process as a surplus —
        and then waits for the child to present itself, so the rungs below it
        (the folds) reason on a pool the widening has already reached.

        Every step is re-asked at execute time what the build could only ask of
        an older pool. A freeze whose user has since raised the per-user barrier
        is skipped — the freezer's own contract is that a move in flight answers
        False and the plan carries on, and it is not the plan's business to
        raise. A spawn is skipped when the pool has meanwhile reached
        ``max_workers`` or already has a child on its way, the guards
        ``rebalance_spawn`` applies to its own scale-up — and a PROBE spawn is
        skipped outright once the restriction it exists to lift has been lifted
        by somebody else. A skip is not a failure: the plan goes on to the rung
        below.

        A step that REPORTS its failure ends the plan exactly like one that
        raises, and for the same reason: what failed is the pool's ability to
        put a fresh process up, so every step ordered after it was decided
        against a world that no longer holds. A replace escalates first — the
        soft succession is given its 30 seconds, then ``hard_restart`` — and
        only a pool that refuses even that aborts, leaving ``pool_status``
        ``restricted`` behind it. The next tick re-reads the world and decides
        again: that is the only retry there is.
        """
        try:
            for step in plan:
                if step["op"] == "freeze":
                    if step["user"] in self.moving:
                        continue
                    await self.freeze_user(step["user"])
                elif step["op"] == "rebalance":
                    await self.rebalance_pass()
                elif step["op"] == "replace":
                    if not await self.recycle_worker(step["worker"], spawn=step["spawn"]):
                        if not await self.hard_restart(step["worker"]):
                            # Anomaly-channel emitter (issue #19).
                            self.logger.error(
                                "plan aborted: %s step failed on %s", step["op"], step["worker"]
                            )
                            self.pool_status = "restricted"
                            return
                elif step["op"] == "spawn":
                    if step.get("probe") and self.pool_status == "ready":
                        continue
                    if self.max_workers is not None and self.target >= self.max_workers:
                        self.logger.warning(
                            "Pool full at max_workers=%s; the plan cannot spawn",
                            self.max_workers,
                        )
                        continue
                    if len(self.living_workers) > len(self.active_workers):
                        continue
                    self.target += 1
                    child = self.spawn_worker()
                    try:
                        await self.wait_worker_ready(child)
                    except TimeoutError:
                        self.target = max(0, self.target - 1)
                        if self.worker_roster[child]["status"] != "dead":
                            self.retire_worker(child)  # who opens a manoeuvre closes it
                        # Anomaly-channel emitter (issue #19).
                        self.logger.error(
                            "plan aborted: %s step failed on %s", step["op"], child
                        )
                        self.pool_status = "restricted"
                        return
                    self.logger.info("Plan widened the pool to %s workers", self.target)
                else:
                    worker = step["worker"]
                    if worker not in self.active_workers or worker == self.reception:
                        continue
                    if self.capacity_headroom(exclude=worker) <= self.compaction_margin:
                        continue
                    if not await self.drain_worker(worker):
                        self.logger.warning(
                            "Compaction skipped: worker %s did not drain, keeping it", worker
                        )
                        continue
                    self.retire(worker)
                    self.logger.info(
                        "Compaction retired worker %s; target is %s", worker, self.target
                    )
        finally:
            self.release_plan()

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

    def spawn_pool_pass(self, pass_coroutine: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """Run one pool pass detached: the caller never waits on what it started.

        The loop holds only a weak reference to a task, so the set is what keeps
        the pass alive; the caller returns at once. The only caller left in the
        package is ``close_request``.
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
        ends: the next planner tick, one ``decision_interval`` later (300s by
        default), finds a fresh, empty worker and sheds onto that.

        With a target, each hot worker from the hottest down hands over the users
        ``pick_rebalance_users`` names for it, one whole ``move_user`` each. A move
        that does not land ENDS the pass: the pool just changed under the readings
        this pass was decided on. Nothing is ever retired here — a rebalance
        levels the pool, only the compaction narrows it.
        """
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

    def pick_rebalance_target(self, total_excess: float) -> str | None:
        """The one worker that absorbs the whole excess, or None when nobody can.

        A candidate is a NON-reception worker that is not hot itself and whose
        saturation still sits under ``1.0 - rebalance_margin`` once the whole
        excess has landed on it — a target filled up to the gate would be the hot
        worker of the next planner tick. Among those the FULLEST wins: placement consolidates
        rather than spreads (R5), so the shed users pack onto a worker already
        carrying its share and the emptier rows stay foldable.

        A ``retiring`` worker is never eligible: the plan in flight folds or
        replaces it, and shedding onto it would hand the very next step a drain
        of the users this one just carried over.
        """
        ceiling = 1.0 - self.rebalance_margin
        saturation = self.evaluator.worker_saturation
        eligible = [
            name
            for name in self.active_workers[1:]
            if self.worker_roster[name]["status"] != "retiring"
            and saturation(name) <= self.worker_threshold(name)
            and saturation(name) + total_excess <= ceiling
        ]
        if not eligible:
            return None
        return max(eligible, key=self.evaluator.worker_load)

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

        A user already being carried is never picked: its hold would make the
        move answer False and end the pass on a user somebody else is moving
        anyway.
        """
        weights = {
            user: weight
            for user, weight in self.rebalance_weights(worker, now).items()
            if user not in self.moving
        }
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
        exactly the target the next planner tick needs, one ``decision_interval``
        later (300s by default).
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

    def capacity_headroom(self, exclude: str | None = None) -> float:
        """The ledger ``C - O``: how much room the pool has beyond what it holds.

        ``C`` is what the pool may take — the reception up to its own threshold
        plus a whole gate for every other worker — and ``O`` is what it holds,
        summed in QUANTITY (``worker_load``): the ledger asks how much fits, not which
        resource binds. A pool with no active worker has no capacity to report.

        ``exclude`` reads the same ledger WITHOUT one worker, as if it were
        already gone: the question a retirement asks before it commits.
        """
        active = [name for name in self.active_workers if name != exclude]
        if not active:
            return 0.0
        capacity = self.reception_threshold + (len(active) - 1) * 1.0
        occupied = sum(self.evaluator.worker_load(name) for name in active)
        return capacity - occupied

    def workers_occupancy_metric(self, workers: Sequence[str]) -> tuple[float, float]:
        """``workers``: worker names. Returns ``(occupancy, reserve)``: the load
        they carry and the capacity they contribute — ``reception_threshold``
        for the reception, 1.0 for any other worker. Modifies nothing.
        """
        reception = self.reception
        occupancy = sum(self.evaluator.worker_load(name) for name in workers)
        reserve = sum(
            self.reception_threshold if name == reception else 1.0 for name in workers
        )
        return occupancy, reserve

    def necessity_candidates(self) -> list[str]:
        """The active workers whose live-memory floor has reached its budget.

        The floor is what the process will not give back, so a floor at
        ``memory_limit_mb * floor_limit_ratio`` is a worker that has spent what
        it was given: its replacement is a NECESSITY. Read off the last archived
        floor (``worker_floors``) — a worker that has closed no window yet, and a
        commander with no ``memory_limit_mb`` at all, have no necessity to
        answer for.
        """
        if not self.memory_limit_mb:
            return []
        budget = self.memory_limit_mb * 1024 * 1024 * self.floor_limit_ratio
        candidates = []
        for name in self.active_workers:
            floors = self.worker_floors(name)
            if floors and floors[-1]["floor"] >= budget:
                candidates.append(name)
        return candidates

    def convenience_candidates(self) -> list[str]:
        """The active workers holding memory they are not using, worst first.

        The waste is what the last occupancy report shows the process keeping
        over its live floor — ``rss`` minus ``rss - reusable`` — measured against
        that floor: over ``waste_ratio`` the replacement buys back memory the
        worker was never going to return, which is a CONVENIENCE, not an
        emergency. A report with no ``rss`` reading, or a floor of zero, weighs
        nothing and never qualifies.
        """
        wastes: dict[str, float] = {}
        for name in self.active_workers:
            window = self.worker_window(name)
            if not window:
                continue
            report = window[-1].get("report") or {}
            rss = report.get("rss")
            if rss is None:
                continue
            floor = rss - (report.get("reusable") or 0)
            if floor <= 0:
                continue
            waste = (rss - floor) / floor
            if waste > self.waste_ratio:
                wastes[name] = waste
        return sorted(wastes, key=lambda name: wastes[name], reverse=True)

    def empty_workers(self) -> list[str]:
        """The active workers holding no user at all, in spawn order.

        The reception is never one of them: it is the guests' worker whatever it
        holds, and the pool always keeps that one address.
        """
        reception = self.reception
        return [
            name
            for name in self.active_workers
            if name != reception and not self.users_on(name)
        ]

    def pick_best_fit(self, weight: float, exclude: str | None = None) -> str | None:
        """The FULLEST active worker that still takes ``weight``, ``None`` if none does.

        Placement packs rather than spreads: among the workers whose saturation
        plus the incoming weight stays under the candidate's OWN admission
        ceiling — ``worker_threshold``, so the reception is never filled past the
        lower gate it is judged at — the answer is the one with the LEAST room
        left: a 10-weight user goes to the worker with 40 free, not to the fresh
        one with a whole gate free, so the fresh one stays available for what
        only it can take. ``exclude`` leaves the condemned worker out: it is the
        one the users are leaving.

        A ``retiring`` worker never fits anything: a plan in flight has already
        named it, so admitting a user there would only queue another move. This
        is also what stops a condemnation gate from counting, as a receiver, a
        worker an earlier step of the SAME plan is taking out.
        """
        saturation = self.evaluator.worker_saturation
        fitting = [
            name
            for name in self.active_workers
            if name != exclude
            and self.worker_roster[name]["status"] != "retiring"
            and saturation(name) + weight < self.worker_threshold(name)
        ]
        if not fitting:
            return None
        return max(fitting, key=saturation)

    async def drain_worker(self, worker: str) -> bool:
        """Move every user off ``worker``; returns whether it ended up empty.

        Each user goes to its own admission-rule target, decided one move at a
        time: the previous arrival changed what the pool reads. A user that left
        by itself in the meantime — swept with a death, or moved by somebody else
        — is nobody's move any more. One refused move ends the drain: the caller
        retires on the strength of this answer.

        The idle go FIRST — a user with nothing pending quiesces at once, while
        a busy one holds the whole drain on its quiesce budget — and the order
        is alphabetical within each tier, so a drain is reproducible.
        """
        for user in self.drain_order(worker):
            if self.user_worker_map.get(user) != worker:
                continue
            target = self.pick_compaction_target(worker)
            if target is None:
                self.logger.warning("Drain of %s: no other worker to take %s", worker, user)
                return False
            if not await self.move_user(user, target):
                return False
        return not self.users_on(worker)

    def drain_order(self, worker: str) -> list[str]:
        """The users of ``worker`` in the order a drain takes them: idle first.

        Two alphabetical tiers — the users whose half-row has nothing pending,
        then the rest. A user already being carried is left out: its hold would
        make the drain's move answer False and abort the whole fold, where
        leaving it simply means the worker does not end up empty and is kept.
        """
        rows = self.worker_roster[worker]["users"]
        return sorted(
            (user for user in rows if user not in self.moving),
            key=lambda user: (bool(rows[user]["pending"]), user),
        )

    def pick_compaction_target(self, drained: str) -> str | None:
        """Where one user of ``drained`` belongs: the best-fit rule, once.

        Every condemnation places by R4: the FULLEST worker that still admits one
        more (``pick_best_fit``), so the pool packs instead of spreading and a
        fresh worker stays available for what only it can take. The weight asked
        for is the bare admission — the drain moves ONE user and re-reads, so the
        question at each step is who has room now, not who could hold the whole
        worker.

        With nobody admitting, the least loaded of all takes the user anyway: the
        ledger already promised the pool fits, so a gate closed everywhere is a
        reading in flight, not a reason to abandon the user. A ``retiring``
        worker is out of that fallback too: the same plan is taking it away, and
        the user would be drained a second time. None only when ``drained`` is
        the whole pool.
        """
        candidates = [
            name
            for name in self.active_workers
            if name != drained and self.worker_roster[name]["status"] != "retiring"
        ]
        if not candidates:
            return None
        best = self.pick_best_fit(0.0, exclude=drained)
        return best if best is not None else min(candidates, key=self.evaluator.worker_load)

    # ------------------------------------------------------------------
    # Recycling — replacing a worker whose live memory is heading for the limit
    # ------------------------------------------------------------------

    def advance_evacuations(self) -> None:
        """Close the books of the open evacuations — cheap, synchronous, per tick.

        The moves do not live here: the idle users travel with the opening
        pass, and everyone else self-delivers the instant their last call
        closes (``close_request`` → ``evacuate_user``). What is left for the
        tick is bookkeeping — retire a worker that stands empty, and report
        one that the pool's own clocks should have freed by now. Neither holds
        a flag, so a lingering evacuation never starves the other forces.
        """
        for name, entry in list(self.worker_roster.items()):
            if entry["status"] != "evacuating":
                continue
            if not entry["users"]:
                self.retire_worker(name)
                self.logger.info("Evacuation of %s complete: retired", name)
                continue
            self.warn_stalled_evacuation(name)

    async def evacuation_pass(self, worker: str) -> None:
        """Move whoever is ready to leave ``worker``; retire it the moment it empties.

        Only the users with nothing pending move NOW — a straggler mid-call is
        skipped without waiting, and a later planner tick — one
        ``decision_interval`` away, 300s by default — catches it once its call has
        closed or the pool's own inactivity clocks have cassated it. One failed
        move ends the step (the pool changed under it); the next tick resumes.
        A worker that stops being ``evacuating`` mid-step — it died, and the
        row belongs to ``channel_lost`` — ends the step too, touching nothing.

        A straggler still aboard when the step ends is not this pass's
        problem: a later tick re-reads the row, and a stall past the pool's own
        clocks is what ``warn_stalled_evacuation`` reports.
        """
        entry = self.worker_roster[worker]
        for user in self.drain_order(worker):
            if entry["status"] != "evacuating":
                return
            if self.user_worker_map.get(user) != worker:
                continue
            if entry["users"].get(user, {}).get("pending"):
                continue
            target = self.pick_compaction_target(worker)
            if target is None or not await self.move_user(user, target):
                return
        if entry["status"] == "evacuating" and not self.users_on(worker):
            self.retire_worker(worker)
            self.logger.info("Evacuation of %s complete: retired", worker)

    def warn_stalled_evacuation(self, worker: str) -> None:
        """Report an evacuation the pool's own clocks should have freed by now.

        The stall itself is measured against ``CONNECTION_MAX_AGE`` — the
        inactivity clock that should have freed the worker — while the repeat is
        throttled to one report per ``EVACUATION_WARN_INTERVAL``: the condition
        does not change from one tick to the next, and the report is for a
        human, not a log
        flood. Destination when the server grows its anomaly channel: that
        channel; the WARNING is its stand-in.
        """
        entry = self.worker_roster[worker]
        now = time.monotonic()
        since = entry["evacuating_since"]
        if since is None or now - since < CONNECTION_MAX_AGE:
            return
        warned = entry["evacuation_warned_at"]
        if warned is not None and now - warned < EVACUATION_WARN_INTERVAL:
            return
        entry["evacuation_warned_at"] = now
        self.logger.warning(
            "Evacuation of %s stalled past the inactivity clocks: %s still aboard "
            "with calls that never close",
            worker,
            sorted(self.users_on(worker)),
        )

    async def recycle_worker(self, name: str, spawn: bool = True) -> bool:
        """Replace one worker: fresh process up, users carried over, source out.

        Two branches, and they differ on the target: with ``spawn=True`` the
        target stays as it is (the replacement covers the source one for one),
        with ``spawn=False`` the target follows the source out and the pool
        narrows by one. Both are detailed below.

        A leaking worker is not killed and mourned, it is SUCCEEDED — the
        replacement is spawned and awaited active BEFORE anything moves, so the
        pool never narrows for the sake of its own hygiene. The ``evacuating``
        flag takes the source out of ``active_workers``, hence out of every
        placement, rebalance and compaction picker and out of the positional
        reception, while the forwards of the users still resident keep reaching
        it — routing reads ``user_worker_map``, which only the move machinery
        rewrites. Spawning goes through ``spawn_worker`` and the retire through
        ``retire_worker``: on this branch the TARGET stays as it is — the
        replacement covers the flagged source, one for one, until the retire
        closes the books.

        THE SICK WORKER IS FLAGGED ONLY AFTER ITS SUCCESSOR HAS REGISTERED — so
        a replacement that never comes leaves it untouched, with nothing to
        roll back, by construction. That failure is not the recycling's to
        manage: the pool cannot regenerate, which is a health condition — the
        recycling closes its own stillborn (who opens a manoeuvre closes it),
        says so loudly in the log, and ends. Nothing is stamped: the failure
        leaves no state behind, and the next planner pass re-reads the world and
        decides again.

        Past the flag there is no way back: an evacuation is a state that
        CONVERGES, not an attempt that can fail. The first pass runs here; the
        stragglers are the planner tick's business (``advance_evacuations``,
        once per ``decision_interval``), and each
        of them either finishes its call and moves, or stops generating traffic
        and is cassated by the pool's own inactivity clocks — the worker
        retires itself the moment it stands empty. Every write to the row
        re-reads it first: a row ``channel_lost`` stamped ``dead`` is its.

        ``spawn=False`` is the branch the weight gate (R4) opens when the rest of
        the pool already takes this worker's users with margin: no new process at
        all, the source is condemned and evacuated, and the POOL NARROWS BY ONE —
        the target follows the worker out, or the reconcile would spawn back the
        very process the gate said was not needed. Nothing is awaited before the
        flag here because there is nothing to wait for: a pool that can absorb
        the users cannot fail to regenerate.
        """
        entry = self.worker_roster.get(name)
        if entry is None:
            raise KeyError(f"no such worker to recycle: {name!r}")
        if self.worker is not None and name == self.worker.name:
            raise ValueError(f"worker {name!r} is the in-process worker: not recyclable")
        if entry["status"] not in ("active", "retiring"):
            raise ValueError(f"worker {name!r} is {entry['status']}: not recyclable")
        if spawn:
            replacement = self.spawn_worker()
            try:
                await self.wait_worker_ready(replacement)
            except TimeoutError:
                if self.worker_roster[replacement]["status"] != "dead":
                    self.retire_worker(replacement)
                self.logger.error(
                    "Recycling of %s not opened: replacement %s never registered — "
                    "the pool cannot regenerate right now",
                    name,
                    replacement,
                )
                return False
            if entry["status"] not in ("active", "retiring"):
                self.logger.warning(
                    "Recycling of %s overtaken by its own death (%s)", name, entry["death"]
                )
                return False
            self.logger.info("Worker %s evacuating: succeeded by %s", name, replacement)
        else:
            self.target = max(0, self.target - 1)
            self.logger.info(
                "Worker %s condemned without a replacement: the pool absorbs its "
                "users, target is %s",
                name,
                self.target,
            )
        entry["status"] = "evacuating"
        entry["evacuating_since"] = time.monotonic()
        await self.evacuation_pass(name)
        return True

    async def hard_restart(self, name: str) -> bool:
        """Park the users, kill the worker, put a fresh one in its place.

        The escalation of a replace whose soft succession did not happen: the
        pool had 30 seconds (``READY_TIMEOUT``) to raise a second process beside
        the sick one and could not, which is what a leak that has eaten the
        machine looks like. So the order is inverted — THE SICK PROCESS DIES
        FIRST, and the fresh one is born in the space its death frees. This is
        the DECLARED EXCEPTION to «alive and registered first, condemned after»:
        the guarantee governs the soft path, and this door opens only once that
        path has proved itself impossible.

        Nothing is lost by dying: every user of the worker goes to the freezer
        first, one parcel per user, and a parked user is as safe as it gets —
        the file outlives the whole pool. The refill is LAZY: nobody is woken
        back here. A parked user comes out of its file on its own next request,
        through ``resolve_worker``'s ordinary wake, placed by the ordinary
        rules — a millisecond it would have spent waiting for this loop anyway,
        and no second party racing the client for the same parcel.

        The parking follows ``resolve_worker``'s discipline — await the user's
        hold, re-read the map, then freeze — and a user that still cannot be
        parked (an identity the freezer does not apply to, a hold that does not
        clear) is SKIPPED with a WARNING: its slice dies with the process and
        it comes back at its next login. An accepted, loud loss.

        Returns whether the pool regenerated. False leaves the users parked in
        their files — nothing lost, and their next request wakes them the moment
        a worker exists — and the caller ends the plan on it. A worker that is
        no longer active at all needs no restart: it is already out, the
        reconcile owes the pool its replacement, and the step has nothing to
        fail at.

        The freezer is what makes the parking possible, so a pool with no
        ``frozen_users_dir`` has no hard restart: killing a worker there would
        throw its users' slices away, and this says so instead.

        The seat of the dying worker is HELD across the kill — the target goes
        down with it and back up before the fresh spawn — or the reconcile,
        which reads a shortfall every half second, would put a second process
        up beside the one this restart is about to start itself. A fresh child
        that never registers leaves the target where it is on purpose: the
        reconcile takes over the retrying, and the first REGISTER that lands
        lifts the restriction.
        """
        entry = self.worker_roster[name]
        if entry["status"] not in ("active", "retiring"):
            self.logger.warning(
                "Hard restart of %s: it is %s already, nothing left to restart",
                name,
                entry["status"],
            )
            return True
        if self.frozen_users_dir is None:
            self.logger.error(
                "Hard restart of %s impossible: the freezer is disarmed, so its users "
                "have nowhere to be parked",
                name,
            )
            return False
        parked = 0
        for user in sorted(self.users_on(name)):
            await self.await_move(user)
            if self.user_worker_map.get(user) != name:
                continue
            if await self.freeze_user(user):
                parked += 1
            else:
                self.logger.warning(
                    "Hard restart of %s: %s did not park; its slice dies with the process",
                    name,
                    user,
                )
        self.logger.warning(
            "Hard restart of %s: %s users parked in the freezer, killing the process",
            name,
            parked,
        )
        self.target = max(0, self.target - 1)
        self.retire_worker(name)
        await self.wait_workers_end([name])
        self.target += 1
        fresh = self.spawn_worker()
        try:
            await self.wait_worker_ready(fresh)
        except TimeoutError:
            if self.worker_roster[fresh]["status"] != "dead":
                self.retire_worker(fresh)  # who opens a manoeuvre closes it
            self.logger.error(
                "Hard restart of %s: the fresh worker %s never registered either — "
                "%s users stay parked in the freezer",
                name,
                fresh,
                parked,
            )
            return False
        self.logger.info("Hard restart of %s done: %s took its place", name, fresh)
        return True

    async def wait_worker_ready(self, name: str) -> None:
        """Block until ONE named worker has presented itself; TimeoutError if it never does.

        The named twin of ``wait_workers_ready``, which counts workers instead:
        a recycling waits for its own replacement, not for a headcount that a
        third worker joining could satisfy.

        A worker already terminal — its row stamped ``dead`` (a stillborn cull,
        a scale-down that culled the tail, an exec that failed) — will never
        register: the wait raises at once instead of staring at a tombstone for
        the whole ``READY_TIMEOUT``. A row missing outright cannot happen inside
        the wait's 30s (burial starts an hour after a death), so it stays a loud
        KeyError, not a handled case.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.READY_TIMEOUT
        while True:
            entry = self.worker_roster[name]
            if entry["status"] == "dead":
                raise TimeoutError(f"worker {name} died before registering")
            if entry["status"] == "active":
                return
            if loop.time() >= deadline:
                raise TimeoutError(f"worker {name} not ready within {self.READY_TIMEOUT}s")
            await asyncio.sleep(0.02)
