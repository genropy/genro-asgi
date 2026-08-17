# Notes — orchestration-m3-commander-groups

(Per-phase rationale goes under `## Phase N` headings: why this way, what was
rejected. The `_TBD` names each phase brought to the owner, and the name they
got, belong here too.)

## Phase 1

**The unit judgement of decision (7): `worker_snapshot_ttl` and
`deposit_lock_retry_interval` KEPT as they are.** `user_idle_freeze_delay` was
renamed because the number's unit really changes — it is a policy of the
installation and Phase 5 puts it in the group grammar as
`user_idle_freeze_minutes`, with the conversion at the one comparison that reads
it (`SECONDS_PER_MINUTE`). The other two are technical times in seconds, and they
live in a family of four the plan itself preserves unchanged in Phase 5's
constants list (`PROCESS_PING_INTERVAL`, `PROCESS_PING_TIMEOUT`,
`TRANSFER_START_DELAY`, `DEPOSIT_LOCK_WAIT_LIMIT`) — none of which spells its
unit either. Renaming two of six would fragment the family for no reader's
benefit, and renaming all six was not in this phase. Reversible with one
search-and-replace if the owner wants the suffix everywhere.

**`QUIT_TIMEOUT_SECONDS` is a module constant, not a kwarg** (Phase 5 decision 4
lists it among the constants). Value 30.0 s, the order of `DEPOSIT_LOCK_WAIT_LIMIT`
— it has to cover a real drain (the gate plus one freeze per user). Tests that
need the timeout to fire monkeypatch the module attribute, which works because the
method reads the global at call time; no test-only kwarg was invented for it.

**The order to leave is answered BEFORE the departures run.** `quit()` ends by
closing the wire, so a reply composed after it could never leave the process: the
op poses the flags synchronously, answers (the photo on that reply is the one
showing every user `T`), and only then drains. The M2 e2e used to get there with
`create_task` + `sleep(0)`; the synchronous head (`_flag_everybody_for_departure`,
shared with `quit()` and idempotent because a departure plan takes nobody back
off it) makes it deterministic instead of a race that happens to be won.

**The wait for an ordered death is parked BEFORE the order is sent**, not after
the answer comes back: the child of the drill answers and closes in the same
breath, so a wait parked after the reply would miss its own EOF and turn an
orderly departure into a kill. The known price is the mirror case — `quit_process`
on a wire whose child is already gone raises `ConnectionError` and leaves the wait
parked, so a later wild death of a successor on that same handler would read as
`quitted`. Accepted: a quitting handler does not come back by construction, and
the group reads the state before ordering.

**The REPLY lane DOWN went with `SpaWorker.call()`.** Decision (6) kills the verb;
its parking lot (`_pending`, `_resolve_reply`, `_fail_pending`) and the REPLY
branch of `handle_frame` are that verb's mechanism and had no other producer — a
REPLY arriving at the worker is now denounced as an envelope with no lane, which
is what the asymmetric protocol says it is. The presentation's own reply is read
inline by `send_presentation` and never went through that lane.

**The store change now rides an order going down** (the beat is the one that
always comes), because the EVENT lane that used to carry it is dead. The M2 test
that pushed it with `send_event` was rewritten on a CALL, not deleted: the
behaviour under test — the replica replaced whole — is unchanged.

**No `_TBD` names survive this phase.** Everything new was either already
baptised in the plan (`quit_process`, `ping_now`, the six `state` values,
`QUIT_TIMEOUT_SECONDS`, the three op paths) or private
(`_answer_then_quit`, `_flag_everybody_for_departure`, `_park_death_wait`,
`_settle_death_wait`). `SECONDS_PER_MINUTE` is the only new public constant: it is
a unit conversion, not a decision, and it is named after what it is.
