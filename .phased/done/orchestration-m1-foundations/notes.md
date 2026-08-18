# Notes — orchestration-m1-foundations

## Phase 1
Two decisions surfaced by the executing chat were settled by the foreman
and folded into the plan (owner's standing expectation: the executor
must never ask the user — every choice is pre-made at planning):
1. read surface: bare payload + `get_item_header` (rule 11), no wrapper
   type (rejected: FrozenItem NamedTuple — a new type with nothing to
   carry beyond diagnostics);
2. lock lifecycle: drop_* never touches the lock; release_lock removes
   it and removes the folder when only the lock remains (rejected:
   drop-last-item removing folder+own-lock — two removal points for
   one lock).
Planning lesson for the next macros: batch EVERY baptism and micro-shape
question at plan time (the F39 session did it right; these two slipped).

Choices made during execution that the plan did not settle:
- `user_to_userkey` is REDEFINED in FreezeHandler rather than imported from
  `spa/commander.py`: the new subpackage must not depend on the machine that
  dies at the cutover. Same implementation (`quote(safe="")`), same one-way
  contract; the duplication disappears with the legacy commander.
- The three removals were born as `delete_*`, the only ones in `src/`: the
  owner named `drop_` the house verb (2026-08-16) and they were renamed —
  `drop_user_item`, `drop_connection_item`, `drop_user_folder`.
- `drop_user_item` added beside the two drops the plan listed: adoption
  reads then drops BOTH item kinds, and a user store that could only be
  removed by wiping the whole folder would have forced callers to reach for
  `drop_user_folder` while the connections still matter.
- The item drops were written raising `FileNotFoundError` on a missing file;
  the owner OVERRULED it (2026-08-16): a drop asks for absence, and a thing
  already gone is that same outcome. All three drops are now idempotent —
  `drop_user_folder` additionally verifies the result. The reason that
  settled it: the cleanup after a dead worker is the ordinary caller, and it
  walks over parcels the dead one may or may not have written.
- The connection filename quotes the cid with the same one-way key as the
  user: a cid comes from a cookie, and no value of it may name a file outside
  its folder.
- `user_folders` is a property (naming rule 11: a pure reading with no
  arguments is a noun), scanning directory entries without opening any file —
  the shape the 4-step sweep consumes.

## Phase 2
The phase was executed with three callbacks handed to the connector at
construction (`on_handshake`, `on_event`, `on_closed`). The owner OVERRULED
the shape and the substance behind it on 2026-08-16, in the review that
followed; what is written below is the settled state, with the reasons.

**No callbacks: the wire asks the handler it already holds.** The connector
keeps `self.worker_handler` from birth, so a callback passed in the
constructor was a second road to the same object. The three surfaces the wire
uses, all baptised by the owner, all implemented in Phase 3:
`global_register_item_tytx` (property — the whole global store, TYTX-encoded,
asked at the instant the child presents itself so it is never stale),
`on_child_message(frame)` (an EVENT arrived from the child),
`on_child_lost()` (the wire died on its own). The same string
`global_register_item_tytx` is the key of the reply payload: not a second
name, the same one.

**The store goes WHOLE, and the version number is abolished.** The version
existed so a newborn could tell which deltas were already inside its snapshot.
The owner ruled that the master replaces the replica entire — at the
presentation like at every later change — so there are no deltas to order and
nothing to number. The measured ground: the global store is kilobytes and
changes about once every three hours, so resending all of it to every worker
costs nothing. This AMENDS design v3 §12 ("delta, FIFO per filo" and "numero di
versione su ogni variazione") and kills the `genroasgi_global_store_version`
metric of §13.2.

- `wait_connected()`: Phase 3 says "spawn → wait handshake (via
  WorkerConnector) → serving", so the wait needs a surface. It is the mirror
  of `ChannelClient.wait_closed()` and, like it, carries no deadline of its
  own — the caller wraps it in its own `asyncio.wait_for`.
- The child's presentation payload (pid, config echo) is no longer handed to
  anybody: it reaches the log. Nothing consumes it today, and Phase 3 can
  expose a reading on the connector if it turns out to need it.

## Phase 3
Everything the baptism round settled was implemented literally. What follows is
what the plan did not settle and the executor had to choose — and, at the end,
what it refused to choose.

**Choices made during execution.**
- `entry_module` (required) and `executable` are constructor parameters: the
  legacy pins the child's entry point as a module constant
  (`WORKER_ENTRY_MODULE`), but the new child does not exist until Macro 2 and
  Phase 4 has to start a scripted stub through this very chain. `executable`
  is the legacy commander's own parameter name, `entry_module` is derived from
  the legacy constant. OPEN for the owner: per-handler parameter or constant of
  the subpackage.
- The handshake deadline is `process_ping_timeout`. Phase 2 left the deadline
  "to whoever waits for the handshake after a spawn" — that is
  `launch_process` — and the alternative was coining a second grammar name.
  One number for "how long silence from this process is tolerated", which is
  also the low-tolerance doctrine. A real child's boot may want more.
- The beat travels on `OCCUPANCY_OP_PATH = "/op/occupancy"`, the ratified
  legacy path REDEFINED with the same value (the precedent of `user_to_userkey`
  in Phase 1 and of CALL/REPLY/EVENT in Phase 2). Nothing was coined: the
  design leaves "the photo's key in the envelope" as a declared `[BATTESIMO]`,
  so the photo is read where the legacy probe reads it — the reply's `result`.
  Consequence: `worker_snapshot` is fed by the beat only, never yet by a photo
  riding an ordinary reply.
- Nobody drives the beat. `ping_process()` is ONE beat carrying the whole
  low-tolerance chain; `process_ping_interval` is held as the cadence and read
  by nobody in `src/` yet. A loop task would have needed a fifth public name
  (the legacy calls it `caretaker`), and `launch_process` is specified as
  "open the wire, spawn, wait" with no watchdog in it.
- A bare `terminate_process()` is NOT a governed death: the plan marks governed
  inside `restart_process()` and nowhere else, so the wire's end denounces it.
  A test pins the semantics. When Macro 2 writes the handler-closure verb it will
  have to mark the death the same way, or the mark moves into
  `terminate_process`.
- `LocalWorkerHandler` refuses FOUR orders, not the three the plan lists: a
  local handler that forked a child would be the very thing F21 excludes, and the
  attach of the in-process worker (the skeletons' unbaptised `attach_local`) is
  Macro 2's. It inherits the constructor whole, so it carries a connector it
  never starts and a `uds_url` in its payload that will never be bound.
- The orchestration log is the module logger: the dedicated `orchestration.log`
  with its path, size and rotation is grammar, and the module docstring says
  the file is still owed. Every order and every wild death has its line.
- `hosted_users` is a property returning the LIVE set: the plan calls it a
  property and its single writer (the fold) does not exist yet, so a verb-first
  mutator would have been a name coined for nobody.

**Two defects the independent verification found, both fixed with a
neutralization-proven regression test.**
1. `launch_process` did not refuse a launch over a living process: two children
   under one handler, the newcomer taking the wire while the predecessor stayed
   alive holding its users' memory — the exact thing F22 forbids. It now raises.
2. The governed mark could be left set: on a handler whose process had already died
   wild, `restart_process` set a mark nobody would ever consume, the wait raised,
   and the handler stayed deaf — the NEXT wild death was swallowed silently. The
   mark is now set only when a child is really on the wire, and the wait gives it
   back before raising.

**Advisory only**: mypy reports 4 `union-attr` on `self.process` in
`terminate_process`/`_kill_process_group`. They are the deliberate absence of
guards (a terminate without a process is a caller bug); silencing them would
mean a scoped override in pyproject.toml, which is outside this phase's files.

**The word `seat` was swept out by the foreman after the phase.** The module
had been written calling the WorkerHandler "the seat" — 45 times in `src/`,
plus tests, plan and notes: the English of «posto», which the owner banned on
2026-08-15 and had wiped from the whole design corpus hours earlier. Prose,
test names and the two error messages now say handler / WorkerHandler. The
legacy commander still carries it in four places; it dies in Macro 6.

**The six open points the phase raised, and where each landed** (foreman,
with the owner):
1. *Who drives the beat* — SETTLED by the owner: the **GroupHandler**, one
   periodic task per group, beats fired in parallel and awaited together, and
   only at the silent ones (the group knows whose photo the traffic has just
   refreshed). Reasons: the cadence is already a number of the group grammar,
   and a per-handler loop would have cost a public name for nothing. Design
   v3 §5 amended. `ping_process()` stays one beat, driven from above.
2. *A bare `terminate_process()` is denounced as WILD* — SETTLED by the
   foreman from the register, no owner call needed: the mark must NOT move
   into `terminate_process`, because the kill of a MUTE process is exactly a
   self-ordered kill whose users were never saved — they must get the
   denunciation and the re-login. What makes a death transparent is not who
   pulled the trigger but whether the users were put away first; only the
   caller knows that, so only the caller marks. Macro 2's ordered-closure
   verb (§7.4) will mark it as `restart_process` does.
3. *No burial verb on the handler* — deferred to Macro 2/3 planning: §7.4
   "Chiusura di un WorkerHandler" is where that verb is born and baptised.
4. *The photo's key on an ordinary reply* — stays `[BATTESIMO]`: the worker
   that attaches the photo is Macro 2, and the key is baptised there.
5. *`LocalWorkerHandler` carries a connector and a `uds_url` never bound* —
   deferred: the in-process attach (`LocalChannel`) is Macro 2's, and that is
   where the local variant stops inheriting what it does not use.
6. *`ping_process` lets a dead-wire `ConnectionError` through* — left as is:
   a beat against a wire already down is not the beat's business, the death
   is already travelling by its own road.

## Whole-diff review at finalize (owner + foreman, 2026-08-16)
Six findings on the four phases read as one diff for the first time. What the
owner ruled changed the machine twice, beyond the fixes.

1. **The announcement of a semaphore is DEAD.** The stub announced its lock
   takes upward (`/lock_taken`), in the wrong order and even on a failed take.
   Chasing the order led to the real answer: before anyone touches mario's
   folder, mario is SUSPENDED at the Commander — stopped, calls parked — so the
   vertex already knows who is working on him, and the worker telling it is
   telling it its own news. And at a death nobody chases a list of semaphores:
   the dead worker's users go WHOLE, folder and lock together. So the deposit
   lock goes back to being what it is — internal mechanics: mutual exclusion
   between writers, and the trace of an interrupted write. Design v3 amended in
   five places (§8.3, the freeze cycle, the dead holder's semaphore, the
   Commander's register of announced semaphores — deleted — and rejection 21,
   which stands on its other leg). The stub now takes the lock and says
   nothing; a declared test instrument keeps the EVENT road exercised.
2. **The photo rides EVERY envelope.** Two tests documented opposite contracts
   for `worker_snapshot` after a death, and the real gap was the restart
   window: between the kill and the newborn's first beat, the judge could read
   the dead process's memory and load — the per-connection rows defend
   themselves (the reader crosses them with its indexes; the truth is the mark,
   never the measure) but the process aggregates have no index to cross with.
   The owner's answer was not to clear the photo but to remove the window: a
   `worker_snapshot` slot that any envelope may carry, filed by the wire before
   it even looks at the frame type. The presentation carries the first one, so
   a live process has a photo from birth; in Macro 2 every user entering or
   leaving sends one, because those are the moments the picture changes. The
   beat kept only the question its name asks. Design v3 §7 (E2/F25) amended.
   Side effect: the e2e no longer verifies the presentation by grepping a log
   line — pid and name arrive inside the photo, which is state.
3. The subpackage exported two of its four classes; all four are exported now
   and the tests take classes from the package, protocol constants from the
   modules.
4. `stop()` leaves `_closing` and the handler's `_listening` set forever, so a
   relaunch after a burial would spawn a child against an unbound socket. It
   cannot happen today: nothing in `src/` calls `stop()` — the burial verb of
   §7.4 does not exist yet. Declared FINAL in the docstring instead of guessing
   a state machine; whoever writes that verb decides what "closed" means.
5. Dissolved by finding 2 (see above).
6. `GroupStub` and `wait_for` are duplicated across two test modules and have
   diverged. Left as they are: both die with the stub when Macro 2 brings the
   real GroupHandler.

## Baptism round for Phase 3 (owner, 2026-08-16)
Held BEFORE launching the phase, the lesson of Phase 2 applied: every public
name Phase 3 needs was decided by the owner first, so the executor asks
nobody. The names are listed in the phase's `Decisions:`; what follows is
what the round changed beyond naming.

- **A verb never stands alone** (new house rule from the owner): a method
  name carries its object — `launch_process()`, not `launch()`. Applied to
  every verb baptised here; worth promoting into the meta CLAUDE.md naming
  rules, which today only say "a mutation leads with the verb".
- **The bonifica leaves the WorkerHandler** (owner's correction, mid-round).
  The design gave the handler a cleanup that had to remove semaphores
  "wherever they are" — i.e. write on indexes owned by the Commander. Now
  the handler only denounces (`on_worker_abort`), the group unhooks, the
  Commander cleans. Two consequences: Phase 3 no longer touches the
  FreezeHandler at all, and the death path matches the one-level-up shape
  used everywhere else. Design v3 amended.
- **No counters on the handler.** Read against the §13.2 table: every
  per-worker family is a gauge fed by the photo, every counter is aggregate
  (`orders_total` by kind/outcome, `relogins_total` by cause) and belongs to
  the Commander — which, after the correction above, is also the one doing
  the cleanup it would be counting. The orchestration log (§4.6) carries a
  line per order AND per wild death (owner: a wild death is nobody's order,
  but it is the event that starts everything).
- **`freezed_users` → `frozen_users`**: the F39 folder name was not English.
  No code carried it — only the plan text.
- The 16 Prometheus families of §13.2 stay `[BATTESIMO]`: they are exposed in
  Macro 5, and naming them tonight would have been naming what nothing yet
  produces.
- CALL/REPLY/EVENT are REDEFINED here with the same values instead of
  imported from `channel/hub.py`: same reasoning as Phase 1's
  `user_to_userkey` — the hub dies in Macro 6 and the new subpackage must not
  hold a reference to it. `REGISTER_METHOD`/`REGISTER_PATH`/`Frame`/
  `FrameStream` ARE imported: `channel/frame.py` survives.
- An inbound CALL from the child is logged as an unexpected envelope, exactly
  as the hub does today: the parent side has no ratified CALL consumer, and
  inventing one here would be a protocol decision, not an implementation
  choice.
- A second connection arriving while the wire is taken is refused and closed,
  the resident stays: the hub's ratified precedent for a duplicate. C2
  guarantees the case cannot happen (the successor is spawned only after the
  OS confirms the predecessor's death), so this is the noisy-error branch of
  the weighted-simplicity rule, never a silent replacement.
- No REGISTER timeout on the accept side (the hub has 10s): the deadline
  belongs to whoever waits for the handshake after a spawn, and a child that
  connects and stays mute is exactly what the Phase 3 probe kills.
- No check on the UDS path length: an over-long path fails at `bind` with an
  explicit OSError, which is the error the caller needs. The limit met us in
  the flesh anyway — the tests bind under a short `mkdtemp` root, because
  pytest's `tmp_path` alone is already past the ~100 character cap. That IS
  the reason worker names are short (E17), and the test module says so.

## Phase 4
No source module was touched: the phase is the scripted child and the story
that drives it. What the plan did not settle, and how it was settled.

**The stub is a module of the test package, not a script written at test time.**
Phase 3 wrote its child into a temp directory; here the stub is a real file
(`tests/orchestration/child_stub.py`) started as
`python -m tests.orchestration.child_stub`, with the repository root put on
`PYTHONPATH` by the fixture — the cwd of a pytest run is not guaranteed. The
gain is that the test and the child share the same constants instead of
repeating strings on both sides of the wire.

**The stub's routing keys are its own, and they are NOT baptisms**:
`/take_deposit_lock`, `/write_connection_item`, `/release_deposit_lock`,
`/lock_taken`, `/go_mute`. The parent side of the worker protocol is Macro 2's
and its names are decided there; the one ratified key used is
`OCCUPANCY_OP_PATH` for the beat. Precedent: `/probe`, `/freeze_everybody` and
`/lock_taken` already live in the tests of phases 2 and 3.

- **The parent drives the deposit one CALL at a time** instead of letting the
  child run a script of its own: each REPLY is the proof that the step is over,
  so the parent reads the deposit between steps with no sleep and no race.
- **Two lock takes, not one.** The first is completed and released — the parcel
  stays behind, the folder with it; the second is still held when the SIGKILL
  lands. That is how the picture Macro 3 inherits carries BOTH the parcel and
  the orphan lock the amendment asks to see.
- **The group travels in `worker_kwargs`** (`{"group": "standard"}`): the header
  of a written item wants the writer's group, and the spawn payload has no group
  key. Splitting the name would have been a convention the payload does not
  declare.
- **The photo carries only what the stub really knows** — pid, name, and the
  global store it was handed. No invented memory figure: the store echo is what
  proves the presentation reply arrived, and a real photo's gauges are Macro 2's.
- **The presentation payload is asserted through the connector's log line.**
  Phase 2 ruled that nothing consumes that payload, so the log is where it
  lands; the reverse direction — the whole store reaching the child — is
  asserted through the photo.
- **The mute switch travels as an EVENT from the parent** (`/go_mute`), which
  also exercises `send_event` in the parent-to-child direction. Frames are
  ordered on the one stream, so the child is already mute when the beat arrives.
- **The kill chain is bounded, not measured**: `elapsed < 4 x
  process_ping_timeout`, with the timeout at 1s. A tighter bound would fail on a
  loaded machine, and no bound at all would let a hung chain pass as green.

**What the independent verification caught.** One MECHANICAL finding, fixed
here: the presentation line was pulled out of the captured log with a `next()`
carrying no default. In an `async def` test a `StopIteration` escaping the
coroutine is converted by Python into `RuntimeError: coroutine raised
StopIteration`, so the day the child stops presenting itself the test would have
reported an unrelated crash instead of the assertion that exists to catch
exactly that. The generator now has a default and the failure is an
AssertionError — proven by searching for a line that is never logged. The three
judgment points it raised are on the phase as `> Review:`.

**Neutralization.** Two probes were run against a temporarily patched source,
restored immediately (the phase leaves `src/` untouched): removing the
denunciation from `on_child_lost` fails the test, and adding a cleanup of the
dead one's users to `on_child_lost` fails it on the surviving folder. The
survival assertions are load-bearing — the day any level starts cleaning here,
this test says so.
