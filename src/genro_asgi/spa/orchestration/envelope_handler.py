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
of itself, and the worker events of everything that happened there since the last
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

**Only the presentation is answered with the store.** The one thing the vertex
has to say to a process that just spoke is the global store, and the only process
that has none of it is one that was just born: so the descent carries it when the
envelope is a presentation — recognised by the ``pid`` the child says at birth
and never again — and carries nothing at all otherwise. The REPLICA IS REPLACED
ENTIRE, always, so a newborn is not a special case and nothing can arrive out of
order. How a change of the master reaches a process already alive is not decided
here: the update travels with the sensor that notices the change, which belongs
to the phase of the pages.

**A layer may in principle change the envelope, and today none does.** What
arrives is what the worker said, and altering it would mix the two: whoever reads
it later could not tell a worker event from an addition. But nothing in the shape
forbids a layer from adding, removing or rewriting on the way through, which is
the door deliberately left open for the day a level has to say something to the
level above — which is why the method is called ``work_on_envelope`` and not
something that says reading only.

**The chain is synchronous, and runs where the envelope landed.** Its work is
writes in RAM, so it needs no await and cannot be interleaved: the worker events
of one envelope are applied in the order the child made them, and two envelopes
are applied in the order they arrived. FIFO by construction rather than by
discipline.

**Dispatch by name.** Every worker event carries its protocol name in ``op``, and
a layer that has something to do about it has a method called ``on_<op>``:
``on_new_page``, ``on_user_frozen``, ``on_process_aborted``. A layer with nothing
to do about a worker event simply has no such method — the census of who reads
what is READABLE as the set of methods each class carries. The same name on three
layers is deliberate (``GroupEnvelopeHandler.on_drop_user`` unhooks the placement
while ``CommanderEnvelopeHandler.on_drop_user`` prunes the indexes), so anything
said about one of them cites the class with it.

**The photo is not a worker event.** It travels in its own slot, it is not a
fact that happened but a state that is true, and every layer reads it: the
handler files it as its latest, the group judges whether it needs a round NOW,
the Commander parks the users it shows on their way out. It is read BEFORE the
worker events of the same envelope, which is the order it was taken in.

**Who is on board is kept by the bottom layer.** A handler's ``hosted_users`` is
written HERE and nowhere else: an arrival — a birth or a homecoming from the
freezer — adds him, a departure — the freezer, or gone for good — takes him off.
It is the list a death is settled on, so it is kept where the deaths are read.

**The death is the one worker event born on this side of the wire.** A process
that has ended announces nothing — it is gone. What the handler has instead is
its ``state``, and ``WorkerEnvelopeHandler.report_death()`` turns that
state into the worker event the levels above consume, on the round that reads it.
So a death climbs the same ladder as everything else, and no level learns about
it in a way of its own. That worker event says who died, who was on board and —
decided at the bottom, once, because that is the level holding both the state and
the last photo — which of them are in the freezer and which are lost: an orderly
departure froze whoever its last photo had flagged for cession, even the ones
whose own worker event died with the wire, while a death nobody ordered saves
NOBODY, because a process that went for reasons of its own leaves nothing that
can be trusted. Both deaths are then read the same way at every level above, the
worker event itself carrying the difference: the traces of the lost go, what they
left in the freezer is discarded and counted, and their next request is a
re-login — the declared price of a death nobody ordered.
"""

from __future__ import annotations

from typing import Any

from genro_tytx import to_tytx

from .worker_connector import GLOBAL_STORE_KEY, WORKER_SNAPSHOT_KEY

#: The slot the worker events travel in, as the worker composes it.
WORKER_EVENTS_KEY = "worker_events"

#: What only a presentation carries: the child says its pid at birth and never
#: again. It is what tells the vertex that this envelope is owed the whole store.
PRESENTATION_KEY = "pid"

__all__ = [
    "PRESENTATION_KEY",
    "WORKER_EVENTS_KEY",
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

    def work_on_envelope(self, envelope: dict[str, Any]) -> None:
        """This layer's part of what the envelope carries: the photo, then the worker events.

        Args:
            envelope: the payload as it came off the wire.

        Acts through the ``on_`` methods this layer carries.
        """
        photo = envelope.get(WORKER_SNAPSHOT_KEY)
        if photo is not None:
            self.on_worker_snapshot(photo)
        for worker_event in envelope.get(WORKER_EVENTS_KEY) or ():
            reader = getattr(self, f"on_{worker_event['op']}", None)
            if reader is not None:
                reader(worker_event)


class WorkerEnvelopeHandler(EnvelopeHandler):
    """The bottom layer: the handler's own photo, and the death of its process.

    Args:
        worker_handler: the handler this layer belongs to.
        group_envelope_handler: the layer of its group — the way up.
    """

    def __init__(self, worker_handler: Any, group_envelope_handler: GroupEnvelopeHandler) -> None:
        self.worker_handler = worker_handler
        self.group_envelope_handler = group_envelope_handler

    def __call__(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Work on the envelope for this handler, then hand it up; returns what goes down."""
        self.work_on_envelope(envelope)
        return self.group_envelope_handler(envelope)

    def report_death(self) -> dict[str, Any]:
        """Turn the ended state of this handler's process into the worker event of it.

        Returns:
            The payload that goes down, as the chain composed it — nothing will
            be sent, since the wire this envelope speaks of is gone.

        Raises:
            ValueError: the process has not ended.
        """
        state = self.worker_handler.state
        if state not in ("quitted", "aborted"):
            raise ValueError(
                f"WorkerHandler {self.worker_handler.name}: its process is {state}, not dead"
            )
        users = set(self.worker_handler.hosted_users)
        rows = (self.worker_handler.worker_snapshot or {}).get("users") or {}
        flagged = {user for user, row in rows.items() if row.get("transfer_flag") == "T"}
        frozen = users & flagged if state == "quitted" else set()
        worker_event = {
            "op": f"process_{state}",
            "worker": self.worker_handler.name,
            "users": sorted(users),
            "frozen_users": sorted(frozen),
            "lost_users": sorted(users - frozen),
        }
        return self({WORKER_EVENTS_KEY: [worker_event]})

    def on_worker_snapshot(self, photo: dict[str, Any]) -> None:
        """File the photo as this handler's latest: the gauges everybody judges on."""
        self.worker_handler.worker_snapshot = photo

    def on_new_user(self, worker_event: dict[str, Any]) -> None:
        """A user is in this process now: he is one of this handler's own."""
        self.worker_handler.hosted_users.add(worker_event["user"])

    #: An adoption is an arrival like any other: the state came home from the
    #: freezer instead of from a login, and the process holds him either way.
    on_user_adopted = on_new_user

    def work_on_envelope(self, envelope: dict[str, Any]) -> None:
        """The estimate of every leaver is stamped first: it needs the WHOLE envelope.

        Args:
            envelope: the payload as it came off the wire.

        Acts on the ``user_frozen`` worker events: each is stamped with the
        ABSTRACT occupancy of the worker — the group's own gauge over this
        envelope's photo — split evenly over everybody it held: the photo's
        population plus ALL the leavers of this same envelope, because an
        idleness sweep freezes many between two beats and they travel together.
        Then the base reading: the photo, the events.
        """
        worker_events = envelope.get(WORKER_EVENTS_KEY) or ()
        leavers = sum(1 for we in worker_events if we["op"] == "user_frozen")
        if leavers:
            photo = envelope.get(WORKER_SNAPSHOT_KEY) or self.worker_handler.worker_snapshot or {}
            estimate = self.worker_handler.group_handler.get_occupancy_percent(photo) / (
                len(photo.get("users") or {}) + leavers
            )
            for worker_event in worker_events:
                if worker_event["op"] == "user_frozen":
                    worker_event["occupancy_percent"] = estimate
        super().work_on_envelope(envelope)

    def on_connection_relabeled(self, worker_event: dict[str, Any]) -> None:
        """A login swaps one of its own for another: the guest goes, the person arrives.

        Who is on board is what a wild death is judged on, so a process that dies
        between a login and the tail of its call must not be read as still
        holding a guest the surface has already forgotten.
        """
        self.worker_handler.hosted_users.discard(worker_event["previous_user"])
        self.worker_handler.hosted_users.add(worker_event["user"])

    def on_user_frozen(self, worker_event: dict[str, Any]) -> None:
        """A user has left this process: he is not one of its own any more."""
        self.worker_handler.hosted_users.discard(worker_event["user"])

    #: Leaving for good says the same thing at this rung: he is not in this
    #: process's memory. Where he went is read one layer up, and a row about to
    #: die needs no estimate — the stamp above touches the frozen alone.
    on_drop_user = on_user_frozen


class GroupEnvelopeHandler(EnvelopeHandler):
    """The middle layer: the placement of the group's users, and its own urgency.

    Args:
        group_handler: the group this layer belongs to.
        commander_envelope_handler: the layer of the vertex — the way up.
    """

    def __init__(
        self, group_handler: Any, commander_envelope_handler: CommanderEnvelopeHandler
    ) -> None:
        self.group_handler = group_handler
        self.commander_envelope_handler = commander_envelope_handler

    def __call__(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Work on the envelope for this group, then hand it up; returns what goes down."""
        self.work_on_envelope(envelope)
        return self.commander_envelope_handler(envelope)

    def on_worker_snapshot(self, photo: dict[str, Any]) -> None:
        """Ring the group's wake when this photo cannot wait for the next round."""
        group_handler = self.group_handler
        occupancy_percent = group_handler.get_occupancy_percent(photo)
        if occupancy_percent > group_handler.restart_occupancy_max_percent:
            group_handler.ping_now()

    def on_connection_relabeled(self, worker_event: dict[str, Any]) -> None:
        """A guest logged in: the placement was his alone, and it goes with him."""
        self.group_handler.user_worker_map.pop(worker_event["previous_user"], None)

    def on_user_frozen(self, worker_event: dict[str, Any]) -> None:
        """A user has left for the freezer: his placement is to be assigned again."""
        self.group_handler.user_worker_map[worker_event["user"]] = None

    def on_drop_user(self, worker_event: dict[str, Any]) -> None:
        """A user is gone for good: he has no placement in this group any more."""
        self.group_handler.user_worker_map.pop(worker_event["user"], None)

    def on_process_quitted(self, worker_event: dict[str, Any]) -> None:
        """A death: the frozen are to be assigned again, the lost lose their
        placement, and the worker named by the worker event leaves the group."""
        for user in worker_event["frozen_users"]:
            self.group_handler.user_worker_map[user] = None
        for user in worker_event["lost_users"]:
            self.group_handler.user_worker_map.pop(user, None)
        self.group_handler.drop_worker(worker_event["worker"])

    #: The wild death is read exactly as the ordered one: the worker event
    #: already carries who was saved and who was lost.
    on_process_aborted = on_process_quitted


class CommanderEnvelopeHandler(EnvelopeHandler):
    """The top layer: the indexes of the whole server, and what goes back down.

    Args:
        spa_commander: the vertex this layer belongs to, and the owner of every
            index it writes through.
    """

    def __init__(self, spa_commander: Any) -> None:
        self.spa_commander = spa_commander

    def __call__(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Work on the envelope for the vertex, and answer a presentation with the store.

        Returns:
            The whole store in the form it travels in when this envelope is a
            presentation; nothing at all otherwise.
        """
        self.work_on_envelope(envelope)
        if PRESENTATION_KEY not in envelope:
            return {}
        return {GLOBAL_STORE_KEY: to_tytx(self.spa_commander.global_register, "json")}

    def on_worker_snapshot(self, photo: dict[str, Any]) -> None:
        """Park every user the photo shows on his way out: his next request waits."""
        for user, row in (photo.get("users") or {}).items():
            flag = row.get("transfer_flag")
            if flag is not None:
                self.spa_commander.hold_user(user, f"transfer_flag {flag}")

    def on_new_page(self, worker_event: dict[str, Any]) -> None:
        """A page was born: it belongs to the connection that asked for it, for good."""
        self.spa_commander.page_connection_map[worker_event["page_id"]] = worker_event[
            "session_id"
        ]

    def on_drop_page(self, worker_event: dict[str, Any]) -> None:
        """A page is gone."""
        self.spa_commander.drop_page(worker_event["page_id"])

    def on_drop_pages(self, worker_event: dict[str, Any]) -> None:
        """A cascade took several pages at once — a connection or a user leaving."""
        for page_id in worker_event["page_ids"]:
            self.spa_commander.drop_page(page_id)

    def on_drop_connection(self, worker_event: dict[str, Any]) -> None:
        """A connection is gone: its pages with it, its identity kept (the cookie is eternal)."""
        self.spa_commander.drop_connection(worker_event["session_id"])

    def on_drop_connections(self, worker_event: dict[str, Any]) -> None:
        """Several connections at once — the cascade of a user leaving."""
        for cid in worker_event["session_ids"]:
            self.spa_commander.drop_connection(cid)

    def on_drop_user(self, worker_event: dict[str, Any]) -> None:
        """A user is gone: his row, his connections and whatever was waiting for him."""
        self.spa_commander.drop_user(worker_event["user"])

    def on_connection_relabeled(self, worker_event: dict[str, Any]) -> None:
        """A connection changed owner: the surface says so, and decides nothing."""
        self.spa_commander.relabel_connection(
            worker_event["session_id"], worker_event["user"], worker_event["previous_user"]
        )

    def on_user_frozen(self, worker_event: dict[str, Any]) -> None:
        """A user is in the freezer: the mark goes on, with what he is expected to cost."""
        self.spa_commander.mark_user_frozen(
            worker_event["user"], worker_event.get("occupancy_percent")
        )

    def on_user_adopted(self, worker_event: dict[str, Any]) -> None:
        """A user came home from the freezer: the mark goes off, his waiting is drained."""
        self.spa_commander.mark_user_adopted(worker_event["user"])

    def on_process_quitted(self, worker_event: dict[str, Any]) -> None:
        """The users of a dead process: the frozen are marked — whether their own
        worker event survived the closing wire or not — and the lost are purged."""
        for user in worker_event["frozen_users"]:
            self.spa_commander.mark_user_frozen(user, None)
        self.spa_commander.drop_users(worker_event["lost_users"], cause=worker_event["op"])

    #: The wild death is read exactly as the ordered one, and it names nobody as
    #: saved: whoever was on board is purged, which is the price of it.
    on_process_aborted = on_process_quitted
