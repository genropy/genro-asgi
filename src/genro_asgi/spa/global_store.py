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

"""The global store: one master Bag above, one replica per worker below.

Homogeneity comes from having a SINGLE WRITER — the commander — so there are no
versions and no gate anywhere in here (the legacy master's own comment: "single
writer, pushes to every worker").

- :class:`GlobalStore` is the replica shape: a Bag written from outside. It
  applies what the commander pushes and captures nothing — 2b puts no collector
  on a replica because nothing consumes one (ratified; if a consumer appears it
  is a local attach, not a protocol change).
- :class:`CapturingGlobalStore` is the same Bag under a capture-all
  :class:`~genro_bag.datachange.DataChangeCollector`. Two objects have that
  shape: the commander's MASTER, whose captures are what propagates, and the
  WORKING COPY a lock holder mutates, whose captures are what travels back at
  release.
- :class:`GlobalStoreLock` is the commander's grant of the master: an
  ``asyncio.Lock`` (FIFO by construction, so the waiters are served in order)
  plus who holds it. No lease and no timer — the holder's channel EOF is the
  whole death protocol, and it applies nothing.
- :class:`GlobalStoreLease` is the worker-side hold: one object usable with
  ``with`` or ``async with``, because the vehicle follows the handler (a sync op
  runs on a pool thread, an async one on the loop).

**The changes land once, at the release.** A holder mutates its working copy
freely and the world sees nothing; the drained changes travel with the release
and the commander applies them to the master in one go. That is what makes the
protocol all-or-nothing without any rollback machinery: a holder that dies —
or a body that raises — has written nothing anywhere.

**The grant carries the store.** A lock is granted together with the master's
current content (``to_tytx``, small by ratification), so the holder never has to
ask whether its replica was current: what it mounts IS the master at grant time.
The working copy is hydrated BEFORE its collector attaches — a captured
hydration would ship the whole store back as changes.

**The wire is TYTX.** A change dict carries a node value (a Bag when the write
created an intermediate node) and a ``change_ts`` datetime, so every global-store
payload — snapshot, grant, change batch — travels ``to_tytx(..., "json")`` and is
hydrated by its reader. The three descending paths are declared here because they
are this module's protocol, and both halves of the pair import them from it.
"""

from __future__ import annotations

import asyncio
import uuid
from types import TracebackType
from typing import Any

from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_tytx import from_tytx, to_tytx

__all__ = [
    "GLOBAL_CHANGES_PATH",
    "GLOBAL_GRANT_PATH",
    "GLOBAL_SNAPSHOT_PATH",
    "CapturingGlobalStore",
    "GlobalStore",
    "GlobalStoreLease",
    "GlobalStoreLock",
]

#: The bootstrap seed: the whole master, shipped to a worker at its REGISTER so
#: its replica is born aligned and every later change applies on top.
GLOBAL_SNAPSHOT_PATH = "/global/snapshot"

#: The incremental rail: ONE EVENT per worker carrying what the master captured.
GLOBAL_CHANGES_PATH = "/global/changes"

#: The grant of the lock, carrying the master's content with it.
GLOBAL_GRANT_PATH = "/global/grant"


class GlobalStore:
    """A global-store Bag written from outside: the replica shape."""

    def __init__(self, bag: Bag | None = None) -> None:
        """Args:
        bag: the Bag to hold; a fresh empty one when omitted. A caller that
            passes one has already hydrated it — the working copy of a lock.
        """
        self.bag = Bag() if bag is None else bag

    def snapshot(self) -> Any:
        """The whole content, TYTX-encoded for the wire."""
        return to_tytx(self.bag, "json")

    def load_snapshot(self, encoded: Any) -> None:
        """Replace the whole content with a shipped snapshot.

        The Bag itself survives (``worker.global_store`` hands out this very
        object), so a reader holding a reference reads the new content.
        """
        self.bag.clear()
        self.bag.update(from_tytx(encoded, "json"))

    def apply_changes(self, changes: list[dict[str, Any]]) -> None:
        """Apply a drained batch in the order it was captured."""
        for change in changes:
            self.apply_change(change)

    def apply_change(self, change: dict[str, Any]) -> None:
        """One change as a plain write, carrying the producer's own attributes.

        No ``_original_ts``: that residue is Q-D's, for a datachange forwarded
        between two live timelines. The global store has a single writer, so a
        replica has no second instant to reconcile — what the master wrote is
        the whole truth. A delete removes the node: setting None would be a
        different state from *gone*.
        """
        key = change["key"]
        if change["delete"]:
            self.bag.pop(key["path"], _reason=key["reason"])
            return
        self.bag.set_item(
            key["path"],
            change["value"],
            _attributes=change["attributes"],
            _reason=key["reason"],
            _fired=key["fired"],
        )


class CapturingGlobalStore(GlobalStore):
    """A global-store Bag whose every write is captured: the master, or a working copy."""

    def __init__(self, bag: Bag | None = None) -> None:
        """Args:
        bag: an already-hydrated Bag, or None for an empty one. The collector
            attaches AFTER, so nothing that was in the Bag is captured.
        """
        super().__init__(bag)
        self.collector = DataChangeCollector(self.bag)

    def set(self, path: str, value: Any) -> None:
        """Write one path — the capture is what propagates."""
        self.bag.set_item(path, value)

    def delete(self, path: str) -> None:
        """Remove one path — the capture is what propagates."""
        self.bag.pop(path)

    def drain(self) -> list[dict[str, Any]]:
        """The changes captured since the last drain, in capture order."""
        return self.collector.drain()

    def detach(self) -> None:
        """Stop capturing: a released lock's working copy is thrown away."""
        self.collector.detach()


class GlobalStoreLock:
    """The commander's grant of the master: FIFO, one holder, no lease and no timer."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        # The grant in force: its request id, and the worker whose channel death
        # releases it.
        self.holder: str | None = None
        self.holder_worker: str | None = None

    async def acquire(self, worker: str, request_id: str) -> None:
        """Park until the master is this request's, then record whose it is.

        ``asyncio.Lock`` wakes its waiters in arrival order, so the FIFO the
        protocol promises is the primitive's own and nothing here queues.
        """
        await self.lock.acquire()
        self.holder = request_id
        self.holder_worker = worker

    def holds(self, request_id: str) -> bool:
        """Whether this request is the grant in force.

        A release arriving for a grant that is no longer in force is a real
        case, not a protocol violation: the holder's channel died while its
        release was already on the wire, and the death released it first. Such
        a release must apply NOTHING — that is the all-or-nothing rule.
        """
        return self.holder == request_id

    def held_by(self, worker: str) -> bool:
        """Whether this worker is the current holder — the death check."""
        return self.holder_worker == worker

    def release(self) -> None:
        """Let the next waiter in; the caller has established who holds it.

        There is no await between that check and this call, so no grant can slip
        in between the two.
        """
        self.holder = None
        self.holder_worker = None
        self.lock.release()


class GlobalStoreLease:
    """One worker-side hold of the global-store lock: ``with`` or ``async with``.

    The two forms are the same protocol on two vehicles, the way the 2a op
    servicing already splits them: a sync op handler runs on a pool thread and
    blocks it on the worker's loop, an async one stays on the loop. Either way
    the body sees the working copy's Bag, the world sees nothing until the exit,
    and a body that raises applies nothing at all.

    The lease owns its ``request_id``: one lease is one grant, from the request
    that ascends to the release that carries the changes back.

    NEVER open a lease while holding the worker's ``dispatch_lock``: both the
    acquire and the release queue their ascending message on a pool thread
    UNDER that very lock, so a holder would deadlock against itself.
    """

    def __init__(self, worker: Any) -> None:
        self.worker = worker
        self.request_id = uuid.uuid4().hex
        self.copy: CapturingGlobalStore | None = None

    async def __aenter__(self) -> Bag:
        """Acquire on the loop and hand the working copy's Bag to the body."""
        copy = await self.worker.acquire_global_lock(self.request_id)
        self.copy = copy
        return copy.bag

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release on the loop, applying the changes only if the body succeeded."""
        await self.worker.release_global_lock(
            self.request_id, self.copy, apply=exc_type is None
        )

    def __enter__(self) -> Bag:
        """Acquire from a pool thread, blocking it until the grant lands."""
        copy = self.worker.run_on_loop(self.worker.acquire_global_lock(self.request_id))
        self.copy = copy
        return copy.bag

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release from a pool thread, applying only if the body succeeded."""
        self.worker.run_on_loop(
            self.worker.release_global_lock(self.request_id, self.copy, apply=exc_type is None)
        )
