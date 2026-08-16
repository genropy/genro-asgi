# Context: wf/orchestration-m2-worker-process
Parent: main
Mode: interactive

## Objective
Build the new worker process of the SPA orchestration rebuild (design v3,
Macro 2): `SpaWorker` in `spa/orchestration/` — the three registers with the
unified user row, adoption (verdict + connection self-service), the
departures scheme (transfer flags in the photo, worker initiative), the two
thread pools, the http CALL form served through the WsgiSeam, the
time-throttled photo and the three clocks — closed by an end-to-end test on
a real child process. The legacy machine stays untouched (cutover is
Macro 4).

Authority order on any doubt: `temp/interview_handler_2026-08-15.md`
(decision register; **F40 carries every baptism and amendment this plan
uses**) > `temp/design_orchestrazione_v3_2026-08-16.md` (spec, amended
2026-08-16 evening) > this plan. Every public name below was baptised by
the owner on 2026-08-16 during Macro 2 planning — the executor invents
none of them and asks nobody.

## Work Plan
- [x] **Phase 1**: Align the M1 foundations to the F40 ratifications
  > Done: the three ratified retrofits, no behaviour change. (1) Deposit
  > vocabulary: parcels are now `user_register_item.pickle` and
  > `connection_register_item_<cid>.pickle`, the six FreezeHandler verbs
  > carry the `register_item` word (`write_/read_/drop_` × user/connection)
  > and the two module constants naming those files follow them
  > (`USER_REGISTER_ITEM_NAME`, `CONNECTION_REGISTER_ITEM_PREFIX`); the
  > folder-drop and lock surface (`drop_user_folder`, `take_lock`,
  > `release_lock`, `lock_holder`, `get_item_header`, `user_folders`) is
  > untouched, docstrings updated to the new file names. (2) The beat op is
  > `/op/ping` under `PING_OP_PATH`, and the constant's comment no longer
  > claims the photo rides the beat. (3) `LocalWorkerHandler` removed —
  > class (33 lines), its module-docstring paragraph, the subpackage export
  > and `__all__` entry, its two tests and their `_local_handler` builder;
  > no reference to it survives anywhere in the repo. 47 renamed references
  > across 6 files, 2 tests removed (1738 → 1736).
  > Files: src/genro_asgi/spa/orchestration/freeze_handler.py,
  > src/genro_asgi/spa/orchestration/worker_handler.py,
  > src/genro_asgi/spa/orchestration/__init__.py,
  > tests/orchestration/test_orchestration_freeze_handler.py,
  > tests/orchestration/test_orchestration_worker_handler.py,
  > tests/orchestration/test_orchestration_foundations_e2e.py,
  > tests/orchestration/child_stub.py,
  > .phased/active/orchestration-m2-worker-process/notes.md
  > (`worker_connector.py` needed no change: it names neither the deposit
  > items nor the beat.)
  > Verified: `pytest tests/ -q` 1736 passed, 2 skipped (baseline 1738/2,
  > the delta is exactly the two removed LocalWorkerHandler tests);
  > `ruff check src/ tests/` clean;
  > `grep -rn "user_item.pickle\|connection_item_\|occupancy\|LocalWorkerHandler" src/genro_asgi/spa/orchestration/ tests/orchestration/`
  > returns nothing.
  - Run: opus / low
  - Pattern: the M1 modules themselves (`spa/orchestration/*.py`) — this
    phase renames and removes, it invents nothing.
  - Files: src/genro_asgi/spa/orchestration/freeze_handler.py,
    src/genro_asgi/spa/orchestration/worker_handler.py,
    src/genro_asgi/spa/orchestration/worker_connector.py,
    src/genro_asgi/spa/orchestration/__init__.py,
    tests/orchestration/test_orchestration_freeze_handler.py,
    tests/orchestration/test_orchestration_worker_handler.py,
    tests/orchestration/test_orchestration_worker_connector.py,
    tests/orchestration/test_orchestration_foundations_e2e.py,
    tests/orchestration/child_stub.py
  - Decisions: three ratified retrofits, nothing else.
    (1) Deposit vocabulary (F40 amends F39): parcel files become
    `user_register_item.pickle` and `connection_register_item_<cid>.pickle`;
    FreezeHandler verbs align — `write_user_register_item`,
    `write_connection_register_item`, `read_user_register_item`,
    `read_connection_register_item`, `drop_user_register_item`,
    `drop_connection_register_item` (folder drop and lock surface keep
    their names: `drop_user_folder`, `take_lock`, `release_lock`,
    `lock_holder`, `get_item_header`, `user_folders`). Rationale recorded:
    one word for the thing in RAM and on disk — the register item.
    (2) The beat op renames `/op/occupancy` → `/op/ping`
    (`OCCUPANCY_OP_PATH` → `PING_OP_PATH`): after the whole-diff review
    the photo no longer rides the beat, the old name lied.
    (3) `LocalWorkerHandler` is REMOVED (F40 supersedes F21 — design §2
    "due processi sempre"): class, export, and its tests. The single role
    is dead; minimum deployment is `workers=1` with a real child.
  - Details: mechanical renames plus the class removal, tests updated in
    the same commit. No behaviour change anywhere: the M1 test assertions
    keep passing under the new names.
  - Done: `pytest tests/ -q` green (full suite, count may drop by the
    removed LocalWorkerHandler tests); `ruff check src/ tests/` clean;
    `grep -rn "user_item.pickle\|connection_item_\|occupancy\|LocalWorkerHandler" src/genro_asgi/spa/orchestration/ tests/orchestration/`
    returns nothing.
- [ ] **Phase 2**: SpaWorker — the registers and the unified row
  - Run: opus / high
  - Pattern: `src/genro_asgi/spa/worker.py` (the legacy registers, rows
    and clock stamping being rethought — deep rethink, never verbatim
    transplant); `src/genro_asgi/spa/orchestration/freeze_handler.py`
    (the deposit surface adoption consumes); test style:
    `tests/orchestration/test_orchestration_freeze_handler.py`.
  - Files: src/genro_asgi/spa/orchestration/spa_worker.py,
    src/genro_asgi/spa/orchestration/__init__.py,
    tests/orchestration/test_orchestration_spa_worker.py
  - Decisions: class **`SpaWorker`** (F40; the legacy `UserStickyWorker`
    stays untouched until Macro 6 — no import in either direction).
    Registers: **`user_register` / `connection_register` /
    `page_register`** — the entry is the *register item*; pages live
    under the connection, connections under the user (inverse maps
    internal, written by single mutators). User row states
    `active` / `frozen` / `unfreezing` (F10) — derived states, never
    oracle booleans. The three clocks are INHERITED names:
    `last_refresh_ts` (technical contact — every call stamps it up the
    chain, pings included), `last_user_ts` (human event, the prince),
    `last_rpc_ts` (real call; the surrogate metre until the page
    protocol carries ping kwargs — F32: valve and expiry judge on the
    real clocks, never on `last_refresh_ts`).
    The unified row (D5/F7/F8/F9/F10): request for a user → row `active`:
    serve; `frozen`: pull; unknown: add as `frozen` and pull. The pull is
    ONE travelling call: mark `unfreezing` BEFORE reading (sisters of a
    burst await the transition, never the service), then all in parallel
    (E9). **`adopt_user(user)`** runs ONLY when the envelope authorises it
    — verdict key **`user_frozen`** in the CALL payload (same predicate as
    the announcement, two directions); **`adopt_connection(cid)`** is
    self-service (F8: no per-connection mark — "beta non ce l'ho: vediamo
    in freezer"). Adoption: read → drop the file (and the folder if last,
    F35) → announce. A non-authorised file is NEVER touched (residue —
    the sweep's business). Announcements are protocol names queued for
    the outbound envelope (`events` sub-envelope, ratified 2026-08-02):
    inherited `new_user`, `new_connection`, `new_page`, `drop_user`,
    `drop_connection`, `drop_connections`, `drop_page`, `drop_pages`;
    new `user_adopted` (turns off the vertex mark at the fold, F6). An
    adopted connection has NO announcement of its own: it emits the
    natural `new_connection`/`new_page` (one creation path, mirror of
    §7.6). The dispatch lock stays single (F28: 2 KB payloads, adoption
    costs microseconds).
  - Details: in-process phase — no wire, no child, no pools yet. The
    deposit is a real FreezeHandler on a tmp dir. Tests tell the row
    story: guest birth (`new_user` guest_<cid> announced), page CALL
    stamping the three clocks up the chain, burst on a frozen row (one
    disk trip, sisters wait on `unfreezing`), verdict-gated user-store
    adoption (authorised → adopted+announced; absent verdict → residue
    untouched), connection self-service (found → rows + natural births;
    not found → empty state, same code line), drops idempotent per the
    house verb.
  - Done: `pytest tests/orchestration -q` green; full suite green;
    `ruff check src/ tests/` clean; no import between `spa_worker.py`
    and the legacy `spa/worker.py` in either direction.
- [ ] **Phase 3**: The departures — freeze cycle, transfer flags, quit
  - Run: opus / high
  - Pattern: `spa_worker.py` as Phase 2 left it;
    `src/genro_asgi/spa/orchestration/freeze_handler.py` (lock + direct
    writes, F39 em.1).
  - Files: src/genro_asgi/spa/orchestration/spa_worker.py,
    tests/orchestration/test_orchestration_spa_worker_departures.py
  - Decisions: **`freeze_user(user)`** — pending empty → folder lock →
    write the register items DIRECT under the lock (no temp, no rename)
    → queue `user_frozen` announcement carrying the placement («X» /
    «nessuno») → release the lock; write failure → ABORT loud (B1): the
    user stays alive where he is. **`freeze_all_users()`** — the async
    mass cycle (B2): one user at a time, the loop breathes between two.
    The departures scheme (F40, four scenarios): at photo composition
    the worker pairs every user row with a **`transfer_flag`** —
    `None` keep / `'T'` cede (memory → fattest, load → costliest,
    preferring no in-flight calls) / `'X'` expired (judged by the worker
    on the REAL clocks for its ACTIVE rows; frozen users belong to the
    vertex). After sending the photo the worker does NOT freeze in the
    same turn: it waits **`TRANSFER_START_DELAY = 2.0`** (module
    constant, NOT config grammar — a technical time, owner's call), the
    certainty that the fold has parked the named users (C1 extended),
    then per user: pending empty → freeze. 'X' rows are dropped with
    their announcements (elimination execution stays F24 at the vertex).
    **`quit()`** — flag everybody 'T' (plus due 'X'), send the photo,
    wait the delay, freeze all at empty pendings, EXIT the process. The
    worker has NO restart verb: rebirth is the handler's
    (`launch_process`, same name and socket) or nobody's — scenarios
    2/3/4 are the SAME worker routine. The idle valve: the worker
    freezes the single idle user beyond **`user_idle_freeze_delay`**
    (config grammar), judged on the real clocks (F32: the ping never
    keeps alive), placement «assegnato a me» (in-place wake). The
    end-of-call hook (D10/E9): at every call close, my user's pendings
    empty + an order on him → execute (freeze). ONE mechanism for two
    uses (closure and departures).
  - Details: still in-process where possible (the photo composition and
    the departure bookkeeping are worker-internal; the announcement
    queue is observable without a wire). The exit of `quit()` is
    testable as "reaches the point of exit" via a seam the e2e will
    exercise for real. Tests: the gate timing (no freeze before the
    delay), the in-flight request landing in pendings and awaited, the
    valve on an eternally-pinging idle user, the B1 abort leaving the
    user alive, the X/T choice honouring the clocks and the measures.
  - Done: `pytest tests/orchestration -q` green; full suite green;
    `ruff check src/ tests/` clean.
- [ ] **Phase 4**: The process shell and the wire
  - Run: opus / xhigh
  - Pattern: `src/genro_asgi/spa/worker_entry.py` (the child bootstrap
    being inherited: env-var payload, orphan detection);
    `src/genro_asgi/spa/worker.py:serve_http` + `spa/environ.py:WsgiSeam`
    (the http form — the seam survives §14 and is consumed as-is);
    `src/genro_asgi/spa/orchestration/worker_connector.py` (the parent
    side of the wire, and the `worker_snapshot` slot precedent).
  - Files: src/genro_asgi/spa/orchestration/spa_worker.py,
    src/genro_asgi/spa/orchestration/worker_entry.py,
    src/genro_asgi/spa/orchestration/__init__.py,
    tests/orchestration/test_orchestration_spa_worker_process.py
  - Decisions: the child entry (heir of legacy `worker_entry.py`, new
    module in the subpackage): reads the 7-key spawn payload from
    `GENRO_ASGI_WORKER`, builds the `worker_class` with its `kwargs`,
    connects to `uds_url`, presents itself (pid, config echo), receives
    the WHOLE global store under `global_register_item_tytx`, declares
    storage sync (`set_sync()`, E19/D22). `entry_module`/`executable`
    stay WorkerHandler constructor parameters fed from above (F40: group
    grammar information — the handler receives, no defaults of its own).
    Two thread pools from the payload sizes: `main_threadpool_size`
    (traffic — WSGI stitching, long calls) and `aux_threadpool_size`
    (service — orders + deposit IO, much smaller; F26). Deposit IO runs
    on the service pool, NEVER on the loop (B2/E19); a busy folder lock
    is awaited as a coroutine ON THE LOOP retrying at
    **`deposit_lock_retry_interval`** (config grammar, F27). Op routing:
    **`/op/ping`** answers the aliveness beat (no photo attached by
    duty); the http CALL form (payload key `http`, identity beside it)
    goes to the WsgiSeam on the traffic pool through the unified row
    first — resolve user/connection on the row (adoption included, the
    verdict read from the SAME payload), stamp the clocks, then stitch;
    `wsgi_app` is the consumer seam, `None` on `SpaWorker` (refused with
    the explicit error, as legacy) and assigned by subclasses — the
    genropy-asgi bridge contract. The photo: **`worker_snapshot`** slot
    on ANY outbound envelope — attached to the presentation (a live
    process has a photo from birth), on EVERY population change (user
    enters or leaves), and on any reply when older than
    **`worker_snapshot_ttl`** (config grammar, ~500 ms cited — F25
    throttle, stamp of last send). Content: process aggregates +
    per-connection three-clock rows + per-user *(item, `transfer_flag`)*
    pairs. The global store DOWNWARD is the symmetric slot (F40): the
    worker strips `global_register_item_tytx` from any inbound envelope
    before dispatch and replaces the replica whole. Self-defense (D8):
    wire dead or jammed → `quit()` minus the announcement the dead wire
    cannot carry (freeze all, exit); possible because the deposit does
    not pass through the channel.
  - Details: tests drive a REAL SpaWorker child over a real UDS with the
    M1 WorkerHandler as the parent (the group played by a stub as in
    M1). Happy paths: presentation photo present from birth, store
    replica replaced via the symmetric slot, `/op/ping` answered, an
    http CALL served by a tiny WSGI app assigned to the seam, throttle
    honoured (two calls inside the ttl → one photo), population change
    photo. The 'no wsgi_app' refusal. Orphan detection inherited from
    the entry pattern.
  - Done: `pytest tests/orchestration -q` green; full suite green;
    `ruff check src/ tests/` clean.
- [ ] **Phase 5**: Macro 2 end-to-end — the worker lives, departs, dies
  - Run: opus / high
  - Pattern: `tests/orchestration/test_orchestration_foundations_e2e.py`
    (the M1 story test — same narrative style, real child, real UDS,
    bounded timings, neutralization-proven assertions).
  - Files: tests/orchestration/test_orchestration_m2_e2e.py
  - Decisions: one story on a real `SpaWorker` child under a real
    `WorkerHandler`: born (presentation photo, store on board) → serves
    http calls through the seam (a tiny WSGI app; clocks stamped, rows
    born, `new_*` announcements observed) → a user goes idle and the
    VALVE freezes him (photo shows the departure, parcel readable
    through FreezeHandler from the parent side) → his next call carries
    the verdict `user_frozen` and he wakes (adoption, `user_adopted`,
    parcel gone, folder gone if last — F35) → the driver (playing the
    group) asks the worker to leave: **`quit()`** — photo with all 'T',
    the gate delay, freeze of everybody, the process EXITS BY ITSELF →
    the parent relaunches on the same name and socket
    (`launch_process`) and the successor presents itself. The DECLARED
    SEAM is asserted, not worked around: in M2 the quit death is still
    denounced WILD by the handler (`on_worker_abort` reaches the group
    stub) — the governed mark arrives in M3 when the group reads the
    intent; this test is the picture Macro 3 inherits. Timings bounded
    (multiples of the ratified timeouts), never measured exactly.
  - Details: no source module is touched by this phase; if the story
    cannot be told, the defect belongs to an earlier phase and comes
    back as a finding, never as a workaround in the test.
  - Done: `pytest tests/orchestration -q` green AND full suite
    `pytest tests/ -q` green (legacy untouched);
    `ruff check src/ tests/` clean; the e2e runs three times in a row
    with no leftover child process.
  - Verify: now — read the e2e top to bottom as the story of Macro 2:
    every name reads as spoken (SpaWorker, the registers, the verbs,
    transfer_flag), no coined jargon anywhere.

## Notes
- The legacy machine (`spa/worker.py`, `spa/commander.py`,
  `channel/hub.py`, `channel/local.py`) is NOT modified in this macro:
  the new subpackage grows beside it; cutover is Macro 4, removals are
  Macro 6. `WsgiSeam` (`spa/environ.py`) is CONSUMED as-is — it
  survives §14.
- The ratified end goal this macro serves (owner, 2026-08-16): at the
  Macro 4 cutover the genropy-asgi bridge serves legacy traffic on the
  new machine with the same http-in-envelope emulation and the same
  `wsgi_app` seam for its `GenropyWorker` subclass — no remounting.
- What is deliberately NOT here: GroupHandler, Commander, fold,
  placement, mailbox, metronome (Macro 3); the real request chain and
  login (Macro 4); boot/shutdown liturgy and Prometheus (Macro 5). The
  WorkerHandler closure verb is born in M3 with its caller (owner,
  Q11); `GroupStub`/`wait_for` test duplicates die with the real
  GroupHandler in M3.
- Declared seam for M3: a `quit()` death is still denounced wild by the
  handler in M2; the group will set the governed mark on reading the
  departure intent. Phase 5 photographs this.
- New tests are implementation tests (`tests/orchestration/`, own
  `__init__.py`) per the two-kinds rule.
- Language: code/comments/commits in English; no AI/LLM references in
  any persisted output (contractual); commits per house style, no
  co-author lines. The words «posto»/«seat» are banned.
- Phases run in separate agent sessions: they never commit (the
  pre-commit hook refuses unattended sessions — the foreman lands after
  reading the diff) and never ask the owner anything; an undecided point
  stops the phase and comes back as a report.
