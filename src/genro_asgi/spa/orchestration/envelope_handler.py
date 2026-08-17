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

"""The chain of the envelope: three layers, one climb, one descent.

An envelope arrives from a child process — its presentation, or the answer to an
order — and carries two things beside its own payload: the photo the process took
of itself, and the announcements of everything that happened there since the last
envelope. Both have to be READ by three different levels, each for its own
reason, and the levels must read them in the same order every time.

**One layer per level, each holding the next.** ``WorkerEnvelopeHandler`` (one
per handler) hands up to ``GroupEnvelopeHandler`` (one per group), which hands up
to ``CommanderEnvelopeHandler`` (one for the whole server). The next layer is
handed in at construction and never discovered by walking anything — the shape
of the middleware chain, and for the same reason: a second road to an object
already in hand is one road too many.

**The climb is nested calls, the descent is the return.** A layer processes the
envelope, then calls the layer above and brings back what goes DOWN; at the vertex
the climb ends and the answer is composed. The wire writes that answer where there
IS an envelope going down — the reply to a presentation — and drops it otherwise.

**A layer may in principle change the envelope, and today none does.** What
arrives is what the worker said, and altering it would mix the two: whoever reads
it later could not tell an announcement from an addition. But nothing in the shape
forbids a layer from adding, removing or rewriting on the way through, which is
the door deliberately left open for the day a level has to say something to the
level above — which is why the method is called ``work_on_envelope`` and not
something that says reading only.

**The chain is synchronous, and runs where the envelope landed.** Its work is
writes in RAM, so it needs no await and cannot be interleaved: the announcements
of one envelope are applied in the order the child made them, and two envelopes
are applied in the order they arrived. FIFO by construction rather than by
discipline.

**Dispatch by name.** Every announcement carries its protocol name in ``op``, and
a layer that has something to do about it has a method called ``on_<op>``:
``on_new_page``, ``on_user_frozen``, ``on_process_aborted``. A layer with nothing
to do about an announcement simply has no such method — the census of who reads
what is READABLE as the set of methods each class carries. The same name on three
layers is deliberate (``GroupEnvelopeHandler.on_drop_user`` unhooks the placement
while ``CommanderEnvelopeHandler.on_drop_user`` prunes the indexes), so anything
said about one of them cites the class with it.

**The photo is not an announcement.** It travels in its own slot, it is not a
fact that happened but a state that is true, and every layer reads it: the
handler files it as its latest, the group judges whether it needs a round NOW,
the Commander parks the users it shows on their way out. It is read BEFORE the
announcements of the same envelope, which is the order it was taken in.

**The death is the one announcement born on this side of the wire.** A process
that has ended announces nothing — it is gone. What the handler has instead is
its ``state``, and ``WorkerEnvelopeHandler.announce_death_TBD()`` turns that
state into the announcement the levels above consume, on the round that reads it.
So a death climbs the same ladder as everything else, and no level learns about
it in a way of its own.
"""

from __future__ import annotations

import logging
from typing import Any

from .worker_connector import GLOBAL_STORE_KEY, WORKER_SNAPSHOT_KEY

#: The slot the announcements travel in, as the worker composes it.
ANNOUNCEMENTS_KEY = "events"

#: The two states of a handler whose process has ended, and the announcement each
#: one becomes: the death somebody ordered, and the death nobody did.
DEATH_ANNOUNCEMENTS = {"quitted": "process_quitted", "aborted": "process_aborted"}

__all__ = [
    "ANNOUNCEMENTS_KEY",
    "DEATH_ANNOUNCEMENTS",
    "CommanderEnvelopeHandler",
    "EnvelopeHandler",
    "GroupEnvelopeHandler",
    "WorkerEnvelopeHandler",
]


class EnvelopeHandler:
    """One layer of the chain: what every layer does with an envelope it is given.

    A layer is CALLABLE, and its own ``__call__`` says the whole shape of it in two
    lines: work on the envelope, then hand it to the layer above — or, at the
    vertex, answer. The layer above is held by whoever HAS one, under its own name,
    so a reader of any layer sees which way is up.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(f"{type(self).__module__}.{type(self).__name__}")

    def work_on_envelope(self, envelope: dict[str, Any], worker_handler: Any) -> None:
        """Do this layer's part of what the envelope carries.

        Args:
            envelope: the payload as it came off the wire — the photo in its own
                slot, the announcements in theirs, the primary answer beside them.
            worker_handler: the handler whose wire it arrived on; every level
                needs to know whose envelope this is.

        The photo first, because it is the state the shot found, then the
        announcements in the order they were made. What this layer has nothing to
        do about it does not carry a method for, and skips.
        """
        photo = envelope.get(WORKER_SNAPSHOT_KEY)
        if photo is not None:
            self.on_worker_snapshot(photo, worker_handler)
        for announcement in envelope.get(ANNOUNCEMENTS_KEY) or ():
            reader = getattr(self, f"on_{announcement['op']}", None)
            if reader is not None:
                reader(announcement, worker_handler)

    def on_worker_snapshot(self, photo: dict[str, Any], worker_handler: Any) -> None:
        """This layer's reading of the photo — every level has one, so this raises."""
        raise NotImplementedError(f"{type(self).__name__} does not read the photo")


class WorkerEnvelopeHandler(EnvelopeHandler):
    """The bottom layer: the handler's own photo, and the death of its process.

    Args:
        worker_handler: the handler this layer belongs to.
        group_envelope_handler: the layer of its group — the way up.
    """

    def __init__(self, worker_handler: Any, group_envelope_handler: GroupEnvelopeHandler) -> None:
        super().__init__()
        self.worker_handler = worker_handler
        self.group_envelope_handler = group_envelope_handler

    def __call__(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Work on the envelope for the handler that owns this layer, then hand it up.

        Args:
            envelope: the payload as it came off the wire. Whose it is needs no
                saying here: this layer was built for that handler.

        Returns:
            The payload that goes down, as the chain composed it.
        """
        self.work_on_envelope(envelope, self.worker_handler)
        return self.group_envelope_handler(envelope, self.worker_handler)

    def announce_death_TBD(self) -> dict[str, Any]:
        """Turn the ended state of this handler's process into the announcement of it.

        Returns:
            The payload that goes down, as the chain composed it — nothing will
            be sent, since the wire this envelope speaks of is gone, but the
            climb is the same one every envelope makes.

        Raises:
            ValueError: the process has not ended. Whoever calls this read a
                state that says the opposite, and a death announced for a living
                process would take its users away from it.

        The announcement says who died, who was on board, and — decided HERE,
        once, because this is the level that holds both the state and the last
        photo — which of them are in the freezer and which are lost. An orderly
        departure froze whoever its last photo had flagged for cession, even the
        ones whose own announcement died with the wire; a death nobody ordered
        saves nobody, because a process that went for reasons of its own leaves
        nothing that can be trusted.
        """
        state = self.worker_handler.state
        if state not in DEATH_ANNOUNCEMENTS:
            raise ValueError(
                f"WorkerHandler {self.worker_handler.name}: its process is {state}, not dead"
            )
        users = set(self.worker_handler.hosted_users)
        frozen = users & self.get_flagged_users_TBD() if state == "quitted" else set()
        announcement = {
            "op": DEATH_ANNOUNCEMENTS[state],
            "worker": self.worker_handler.name,
            "users": sorted(users),
            "frozen_users": sorted(frozen),
            "lost_users": sorted(users - frozen),
        }
        return self({ANNOUNCEMENTS_KEY: [announcement]})

    def get_flagged_users_TBD(self) -> set[str]:
        """Who the last photo of this process showed on his way out.

        Returns:
            The users flagged for cession when that photo was taken — the ones a
            departure had already promised to the freezer.
        """
        rows = (self.worker_handler.worker_snapshot or {}).get("users") or {}
        return {user for user, row in rows.items() if row.get("transfer_flag") == "T"}

    def on_worker_snapshot(self, photo: dict[str, Any], worker_handler: Any) -> None:
        """File the photo as this handler's latest: the gauges everybody judges on."""
        worker_handler.worker_snapshot = photo


class GroupEnvelopeHandler(EnvelopeHandler):
    """The middle layer: the placement of the group's users, and its own urgency.

    Args:
        group_handler: the group this layer belongs to.
        commander_envelope_handler: the layer of the vertex — the way up.
    """

    def __init__(
        self, group_handler: Any, commander_envelope_handler: CommanderEnvelopeHandler
    ) -> None:
        super().__init__()
        self.group_handler = group_handler
        self.commander_envelope_handler = commander_envelope_handler

    def __call__(self, envelope: dict[str, Any], worker_handler: Any) -> dict[str, Any]:
        """Work on the envelope for this group, then hand it to the vertex.

        Args:
            envelope: the payload as it came off the wire.
            worker_handler: the handler it arrived on — which of this group's it
                was has to be said, because a group has many.

        Returns:
            The payload that goes down, as the vertex composed it.
        """
        self.work_on_envelope(envelope, worker_handler)
        return self.commander_envelope_handler(envelope, worker_handler)

    def on_worker_snapshot(self, photo: dict[str, Any], worker_handler: Any) -> None:
        """Ring the group's wake when this photo cannot wait for the next round."""
        if self.group_handler.snapshot_is_urgent_TBD(photo):
            self.group_handler.ping_now()

    def on_user_frozen(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A user has left for the freezer: his placement is to be assigned again."""
        self.group_handler.record_placement_TBD(announcement["user"], None)

    def on_drop_user(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A user is gone for good: he has no placement in this group any more."""
        self.group_handler.forget_placement_TBD(announcement["user"])

    def on_process_quitted(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """The process left as it was asked to: its users and then its handler."""
        self._bury_worker(announcement, worker_handler)

    def on_process_aborted(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """The process died with nobody waiting for it: the same reading, and nobody saved."""
        self._bury_worker(announcement, worker_handler)

    def _bury_worker(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A death, read as this group reads one: the placements first, the handler last.

        Whoever is in the freezer is to be assigned again — he exists and needs a
        home; whoever is lost has no placement at all any more. Then the handler
        comes out of the group, which is the same verb for both kinds of death.
        """
        for user in announcement["frozen_users"]:
            self.group_handler.record_placement_TBD(user, None)
        for user in announcement["lost_users"]:
            self.group_handler.forget_placement_TBD(user)
        self.group_handler.drop_worker(worker_handler)


class CommanderEnvelopeHandler(EnvelopeHandler):
    """The top layer: the indexes of the whole server, and what goes back down.

    Args:
        spa_commander: the vertex this layer belongs to, and the owner of every
            index it writes through.
    """

    def __init__(self, spa_commander: Any) -> None:
        super().__init__()
        self.spa_commander = spa_commander

    def __call__(self, envelope: dict[str, Any], worker_handler: Any) -> dict[str, Any]:
        """Work on the envelope for the vertex, and answer with the global store.

        Args:
            envelope: the payload as it came off the wire.
            worker_handler: the handler it arrived on.

        Returns:
            The whole store in the form it travels in. There is nobody above the
            vertex, so the climb ends here and this is what goes down: the store
            is the one thing the vertex has to say to a process that just spoke,
            and the REPLICA IS REPLACED ENTIRE, always, so a newborn is not a
            special case and nothing can arrive out of order.

        The wire writes this where there IS an envelope going down — the answer to
        a presentation — and drops it otherwise: an answer is not answered. How a
        change of the master reaches a process that is already alive is not
        decided yet: the write climbs and the update is sent to everybody, and
        both belong to the phase that gives the vertex its groups.
        """
        self.work_on_envelope(envelope, worker_handler)
        return {GLOBAL_STORE_KEY: self.spa_commander.global_register.item_tytx}

    def on_worker_snapshot(self, photo: dict[str, Any], worker_handler: Any) -> None:
        """Park every user the photo shows on his way out of that process.

        A user flagged for cession or for expiry is about to lose the process he
        lives on, so a request of his that arrived meanwhile must not be routed
        there: the hold is what makes it wait for the departure to be over. The
        flag is the worker's own decision, taken at the moment of the photo, and
        this is where the rest of the machine learns it.
        """
        for user, row in (photo.get("users") or {}).items():
            flag = row.get("transfer_flag")
            if flag is not None:
                self.spa_commander.hold_user_TBD(user, f"transfer_flag {flag}")

    def on_new_page(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A page was born: it belongs to the connection that asked for it, for good."""
        self.spa_commander.add_page(announcement["page_id"], announcement["session_id"])

    def on_drop_page(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A page is gone."""
        self.spa_commander.drop_page(announcement["page_id"])

    def on_drop_pages(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A cascade took several pages at once — a connection or a user leaving."""
        for page_id in announcement["page_ids"]:
            self.spa_commander.drop_page(page_id)

    def on_drop_connection(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A connection is gone: its pages with it, its identity kept.

        The cookie is eternal: the browser that comes back on that same cid is
        the same person, so what is dropped is the connection's pages and not
        the row that says whose the cid is.
        """
        self.spa_commander.drop_connection(announcement["session_id"])

    def on_drop_connections(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """Several connections at once — the cascade of a user leaving."""
        for cid in announcement["session_ids"]:
            self.spa_commander.drop_connection(cid)

    def on_drop_user(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A user is gone: his row, his connections and whatever was waiting for him."""
        self.spa_commander.drop_user(announcement["user"])

    def on_user_frozen(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A user is in the freezer: the mark goes on, with what he is expected to cost."""
        self.spa_commander.record_user_frozen_TBD(
            announcement["user"], announcement.get("occupancy_percent")
        )

    def on_user_adopted(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """A user came home from the freezer: the mark goes off, and his waiting is served."""
        self.spa_commander.record_user_adopted_TBD(announcement["user"])

    def on_process_quitted(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """The process left as ordered: whoever it was holding is accounted for.

        An orderly departure freezes everybody and announces every one of them,
        but the last announcements travel on a wire that is closing: the ones the
        announcement names as frozen are in the freezer whether their own
        announcement made it or not, so their marks are written here.
        """
        self._bury_users(announcement)

    def on_process_aborted(self, announcement: dict[str, Any], worker_handler: Any) -> None:
        """The process died on its own: nobody it held can be trusted any more.

        Not knowing WHY it died, every user that was on it is suspect — frozen and
        not alike — which is why the announcement of a wild death names nobody as
        saved: the traces go, what they left in the freezer is discarded and
        counted, and their next request is a re-login. This is the price of a
        death nobody ordered, and it is paid here.
        """
        self._bury_users(announcement)

    def _bury_users(self, announcement: dict[str, Any]) -> None:
        """The users of a dead process: the freezer marks written, the rest discarded."""
        for user in announcement["frozen_users"]:
            self.spa_commander.record_user_frozen_TBD(user, None)
        self.spa_commander.purge_users_TBD(announcement["lost_users"], cause=announcement["op"])
