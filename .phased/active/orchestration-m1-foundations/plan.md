# Context: wf/orchestration-m1-foundations
Parent: main
Mode: interactive

## Objective
Build the foundations of the SPA orchestration rebuild (design v3) in a
new subpackage, without touching the running legacy commander: the
FreezeHandler (the deposit, single point of disk discipline), the
WorkerConnector + per-WorkerHandler UDS endpoint, and the
WorkerHandler/LocalWorkerHandler with low-tolerance surveillance —
closed by an end-to-end foundations test with a real child process.

Spec of record: `temp/design_orchestrazione_v3_2026-08-16.md`.
Decision log (authority): `temp/interview_handler_2026-08-15.md`
(F39 carries the baptisms and the two amendments used here).

## Work Plan
- [x] **Phase 1**: FreezeHandler — the deposit class
  > Done: new `spa/orchestration/` subpackage with FreezeHandler — one folder
  > per user under a 0700 root, direct writes under the `.lock` semaphore
  > (no temp, no rename), bare-payload reads with `get_item_header` beside
  > them, drops that never touch the lock, and `release_lock` as the single
  > point that removes both the lock and a folder left with the lock alone.
  > 14 tests green, full suite 1708 passed, ruff clean, no legacy import in
  > either direction.
  > Files: src/genro_asgi/spa/orchestration/__init__.py,
  > src/genro_asgi/spa/orchestration/freeze_handler.py,
  > tests/orchestration/__init__.py,
  > tests/orchestration/test_orchestration_freeze_handler.py,
  > .phased/active/orchestration-m1-foundations/notes.md
  > Verified: `pytest tests/orchestration -q` 14 passed;
  > `pytest tests/ -q` 1708 passed, 2 skipped; `ruff check src/ tests/` clean.
  - Run: opus / medium
  - Pattern: `src/genro_asgi/spa/commander.py` (`user_to_userkey`, the
    one-way key; `freeze_user` parcel writing as the behaviour being
    replaced); test style: `tests/test_spa_commander.py`
  - Files: src/genro_asgi/spa/orchestration/__init__.py,
    src/genro_asgi/spa/orchestration/freeze_handler.py,
    tests/orchestration/__init__.py,
    tests/orchestration/test_orchestration_freeze_handler.py
  - Decisions: root `.genroasgi/frozen_users/<user>/` (owner 2026-08-16:
    `freezed` was not English; folder name via
    the one-way key); files `user_item.pickle` (user store) and
    `connection_item_<cid>.pickle` (connection + ITS PAGES); semaphore
    `.lock` (created O_CREAT|O_EXCL, holder name written inside);
    NO temp files, NO rename — writes are DIRECT under the semaphore
    (F39 amendment 1: the semaphore is the only coherence mechanism;
    readers wait on the lock, so nobody can see a half file);
    `os.*` used directly INSIDE this class only (F11: "the deposit only
    via the deposit node" — every caller goes through this surface);
    every pickle payload wrapped with a diagnostic header (writer, ts,
    cause, group) — never used to decide adoption;
    dropping the last file of a folder removes the folder (F35);
    folder listing returns a set (the 4-step sweeper of F34 consumes it);
    the async retry-wait for a busy lock belongs to CALLERS on their
    event loop (F27) — this class exposes non-blocking try-acquire plus
    sync primitives for thread-pool use;
    read_* methods return the BARE payload (None if absent) — the
    diagnostic header is read via a separate `get_item_header(...)`
    (rule 11: pure reading with args wears the get_ prefix); no new
    wrapper type;
    drop_* methods NEVER touch the lock: `release_lock` is the single
    point that removes it, and if the folder is then reduced to the
    lock alone it removes the folder too — one invariant: a folder
    exists iff it has items OR an operation is in progress (F35 is
    satisfied at the release of the same operation);
    the removal verb is `drop_` — the house verb everywhere in `spa/`
    (owner, 2026-08-16), and every drop is IDEMPOTENT: it asks for
    absence, and a thing already gone is that same outcome (same
    ratification) — the cleanup after a dead worker walks over parcels
    the dead one may or may not have written.
  - Details: class FreezeHandler(root_path); methods (verb-first for
    mutations, per naming rules): write_user_item / write_connection_item
    (direct write under held lock), read_user_item / read_connection_item,
    drop_user_item / drop_connection_item / drop_user_folder (the last
    one verifying the result),
    user_folders (set, for the sweeper), take_lock(user, holder) →
    bool, release_lock(user, holder), lock_holder(user) → str|None.
    Tests first: mutual exclusion of the lock; simultaneous writers on
    DIFFERENT files of the same folder (login vs whole-freeze layout);
    folder removed with last file; header round-trip; key is one-way
    (no reverse function exists).
  - Done: `pytest tests/orchestration -q` green; `ruff check src/ tests/`
    clean; no import of FreezeHandler from legacy spa modules.
- [x] **Phase 2**: WorkerConnector — the per-WorkerHandler wire
  > Done: `WorkerConnector` — one UDS per WorkerHandler, unlink-before-bind
  > always, socket directory 0700, the presentation answered with the WHOLE
  > global store, CALL parked on the frame id, EVENT served on its own task,
  > REPLY resolved inline, an inbound CALL logged as unexpected; EOF or a
  > protocol violation fails every pending CALL and tells the handler
  > `on_child_lost`, while a deliberate `stop()` announces nothing. The address
  > survives the relaunch: the successor presents itself on the same socket and
  > gets the store as it is at THAT moment. No callbacks are handed in at
  > construction — the wire asks the handler it already holds. 13 tests green on
  > a real loopback UDS, full suite green, ruff clean, no legacy import in
  > either direction (only `channel/frame.py`).
  > Files: src/genro_asgi/spa/orchestration/worker_connector.py,
  > tests/orchestration/test_orchestration_worker_connector.py,
  > .phased/active/orchestration-m1-foundations/notes.md
  > Review: `WorkerConnector` is NOT exported from
  > `spa/orchestration/__init__.py` — that file is outside this phase's Files
  > list, so the tests import the module path. The child's presentation payload
  > (pid, config echo) now reaches the log only: nothing consumes it, and if
  > Phase 3 wants it, it is one reading on the connector to baptise then.
  > Verified: `pytest tests/orchestration -q --no-cov` 28 passed (13 new);
  > `pytest tests/ -q --no-cov` 1709 + 13 green;
  > `ruff check src/ tests/` clean.
  - Run: opus / medium
  - Pattern: `src/genro_asgi/channel/client.py:ChannelClient` (framing
    use), `src/genro_asgi/channel/frame.py:FrameStream`,
    `src/genro_asgi/channel/local.py:LocalChannel` (same surface for the
    in-process role)
  - Files: src/genro_asgi/spa/orchestration/worker_connector.py,
    tests/orchestration/test_orchestration_worker_connector.py
  - Decisions: one UDS socket PER WorkerHandler, path
    `<instance_dir>/<worker_name>.sock`, unlink-before-bind ALWAYS,
    0700 on the socket directory; whoever connects IS the process of
    that WorkerHandler (identity by construction); presentation: child
    sends {pid, config echo} → the reply carries the WHOLE global store
    (F31: the store travels in the presentation, no disk; owner
    2026-08-16: whole replacement, NO delta and NO version number —
    the store is kilobytes and changes about once every three hours,
    so the newborn is not a special case and nothing arrives out of
    order); CALL/REPLY/EVENT framing reused from channel/frame.py — the
    hub (`channel/hub.py`) is NOT touched here (it dies in Macro 6);
    EOF/error on the stream = a LOCAL event told to the handler
    (burial on event, E13); the ChannelHub multi-member logic
    is not replicated: one connector, one stream;
    NO callbacks in the constructor (owner 2026-08-16): the connector
    holds `self.worker_handler` already, so it asks it —
    `global_register_item_tytx` (the whole store, TYTX-encoded, the same
    string used as the key of the reply payload), `on_child_message(frame)`
    for an inbound EVENT, `on_child_lost()` when the wire dies on its own.
  - Details: class WorkerConnector owned by the WorkerHandler
    (attribute `worker_handler.connector`): accept-side endpoint,
    presentation, call()/send_event()/reply routing, the two tellings
    above. Tests on a loopback UDS in a tmp dir: presentation payload,
    call/reply round-trip, event delivery, EOF detection, stale-socket
    unlink-before-bind.
  - Done: `pytest tests/orchestration -q` green; `ruff check src/ tests/`
    clean.
- [x] **Phase 3**: WorkerHandler + LocalWorkerHandler
  > Done: the handler and its process. Four orders, each verb carrying its object —
  > `launch_process` (bind once, spawn, wait for the presentation, kill and raise
  > on a child that never shows up), `terminate_process` (SIGKILL to the process
  > group, await the OS death, no escalation and no grace), `restart_process`
  > (the same name and socket, marking the death GOVERNED so the wire's end
  > announces nothing) and `ping_process` (one beat, ONE repeat past the timeout,
  > then the kill). A wild death is the handler's only denunciation:
  > `on_worker_abort(self)` on `self.group_handler`, with `hosted_users` on
  > board — no cleanup, no deposit, no FreezeHandler anywhere in the module.
  > `worker_snapshot` holds the photo the beat brings back, no counters beside
  > it; `global_register_item_tytx` answers the placeholder until the Commander
  > owns the master; the 7-key spawn payload travels as JSON in
  > `GENRO_ASGI_WORKER`. `LocalWorkerHandler` is the subclass that refuses every
  > process order because its health is the server's. 15 tests on real child
  > processes and real sockets, full suite 1737 passed, ruff clean, no legacy
  > import in either direction.
  > Files: src/genro_asgi/spa/orchestration/worker_handler.py,
  > tests/orchestration/test_orchestration_worker_handler.py,
  > .phased/active/orchestration-m1-foundations/notes.md
  > Review: eight points the executor refused to decide, all in notes.md
  > § Phase 3 — the naming ones first: `entry_module`/`executable` are
  > constructor parameters outside the baptised set (the child the handler starts);
  > the handshake deadline reuses `process_ping_timeout`; the beat's routing key
  > reuses the ratified `/op/occupancy`; the handler has no burial verb (callers
  > reach `connector.stop()`, and `_listening` survives it); nobody drives the
  > beat and `process_ping_interval` is therefore read by no one; a bare
  > `terminate_process()` outside a restart is denounced as WILD (the literal
  > reading of the plan — the handler-closure verb of Macro 2 will need the mark);
  > a beat on an already-dead wire raises `ConnectionError` where the legacy
  > probe absorbed it; an error sub-envelope counts as an answered beat with no
  > photo. Also: `LocalWorkerHandler` inherits the socket connector and answers
  > `spawn_payload` with a `uds_url` that will never be bound; `hosted_users`
  > returns the live set and is the only way to write it; mypy reports 4
  > advisory `union-attr` on `self.process` (the deliberate absence of guards).
  > Verified: `pytest tests/orchestration -q --no-cov` 43 passed (15 new);
  > `pytest tests/ -q --no-cov` 1737 passed, 2 skipped; `ruff check src/ tests/`
  > clean; three behaviours proven by neutralization (drop the governed mark →
  > the restart test fails; one beat instead of two → the mute test fails; mute
  > the denunciation → four death tests fail), and the two defects the
  > verification found were fixed with a regression test each, itself
  > neutralization-proven.
  - Run: opus / high
  - Pattern: `src/genro_asgi/spa/commander.py` spawn/kill machinery
    (`start_new_session=True`, `os.killpg`, the SIGTERM→SIGKILL
    escalation in `wait_workers_end`); config grammar:
    `src/genro_asgi/config/` existing builders
  - Files: src/genro_asgi/spa/orchestration/worker_handler.py,
    tests/orchestration/test_orchestration_worker_handler.py
  - Decisions: EVERY public name below was baptised by the owner on
    2026-08-16, in the round that followed Phase 2 — the executor invents
    none of them and asks nobody.
    *What the wire already calls* (written in Phase 2, implemented here):
    `global_register_item_tytx` (property, the whole global store
    TYTX-encoded; born here with the PLACEHOLDER value
    `'not yet ready --- wait next phase'` and filled for real in Macro 3,
    when the commander that holds the master exists),
    `on_child_message(frame)` (an EVENT arrived from the child),
    `on_child_lost()` (the wire died — where the handler decides whether
    that death was its own).
    *The process, verb-first and never a bare verb* (owner's rule, same day:
    a verb always carries its object): `launch_process()` (open the wire,
    spawn the child, wait for its presentation), `terminate_process()`
    (SIGKILL to the process group, await the OS death), `restart_process()`
    (terminate + launch a fresh one on the SAME name and socket — OS level
    only: no tap, no freezing, no user policy; its one duty beyond the OS is
    to mark the death as GOVERNED so the burial does not treat healthy users
    as castaways), `ping_process()` (the health beat, websocket-analogous —
    distinct from the browser ping of the three clocks).
    *What it owns*: `hosted_users` (property, the users living on ITS
    process — the group reads it), `worker_snapshot` (the last photo the
    child attached to a reply: memory, load, counts, per-connection clocks —
    the picture the judge reads to shape the pool; sibling of the existing
    `app_snapshot`). NO counters of its own (owner, with the §13.2 table as
    evidence: every per-worker metric is a gauge fed by the photo, every
    counter is aggregate and lives at the Commander).
    *Death — RIDETTATA by the owner, the bonifica is NOT here*: a governed
    death (ordered inside `restart_process()`) is transparent and announces
    nothing; a WILD death calls `on_worker_abort(worker_handler)` on
    `self.group_handler` and the handler's job ends there. The group unhooks
    it from the placement, the Commander — the single writer of the maps —
    prunes the traces, discards and counts the parcels, removes the
    semaphores ANNOUNCED by the dead one wherever they are, and its users
    hear "session lost" → re-login. Reason: the semaphores "wherever they
    are" were never this handler's to touch. Consequence for this phase:
    **the FreezeHandler is NOT used here at all**.
    *Spawn payload keys* (JSON in an env var, as today; strings and numbers,
    never objects — E19): `name`, `uds_url` (always UDS: between machines it
    is the subcommanders that speak, design §10), `frozen_users_path`,
    `main_threadpool_size`, `aux_threadpool_size`, `worker_class`, `kwargs`.
    *Config grammar*: `process_ping_interval`, `process_ping_timeout`.
    *Unchanged*: name = `<group_name>_<counter>` (`standard_0001`), counter
    resets at server restart (F39); surveillance = LOW TOLERANCE (C2 full):
    mute ping → ONE repeat past the timeout → SIGKILL → await OS death →
    only then a successor, never two processes under one WorkerHandler
    (F22); every order and every wild death gets a line in the orchestration
    log (§4.6); LocalWorkerHandler SUBCLASS: no ping, no SIGKILL, no
    restart, no self-defense — its health IS the server (F21).
  - Details: lifecycle: `launch_process` → wait presentation (via
    WorkerConnector) → serving; the kill chain; burial (socket unlink).
    The GroupHandler does not exist yet: the handler holds it as
    `self.group_handler` (semantic parent name, rule 7) and calls
    `on_worker_abort` on it, exactly as Phase 2's connector calls this
    class. Tests with a scripted fake child (a tiny python script):
    presentation happy path, mute-ping kill chain on a child that stops
    answering, a wild death reaching a stub group as `on_worker_abort` with
    `hosted_users` readable on the handler, a governed restart announcing
    nothing, LocalWorkerHandler exemptions.
  - Done: `pytest tests/orchestration -q` green; `ruff check src/ tests/`
    clean.
- [ ] **Phase 4**: Foundations end-to-end
  - Run: opus / high
  - Pattern: `src/genro_asgi/spa/worker_entry.py` (today's child
    bootstrap — orphan detection, entry wiring)
  - Files: tests/orchestration/child_stub.py,
    tests/orchestration/test_orchestration_foundations_e2e.py
  - Decisions: the stub is TEST-ONLY (the real worker process is
    Macro 2); it must exercise every foundation: connect + present
    itself (receives the whole global store), answer the beat with a
    photo, announce a lock take (EVENT frame), write a
    `connection_item` under the lock into the deposit it was given in
    `frozen_users_path`, release, then be killed via the WorkerHandler
    chain. AMENDED 2026-08-16 (the owner moved the cleanup to the
    Commander): after the wild kill the handler DENOUNCES and nothing
    else — `on_worker_abort` reaches the group stub carrying the
    handler and its `hosted_users`, and the deposit is left EXACTLY as
    the dead process left it. That untouched parcel and that orphan
    lock are the picture Macro 3 inherits: asserting they survive is
    asserting that Macro 1 cleans nothing.
  - Details: one e2e test telling the full foundations story on a real
    subprocess + real UDS in a tmp dir; assertions on: the presentation
    payload, the photo landing in `worker_snapshot`, deposit contents at
    each step (written under the lock, readable through FreezeHandler
    from the parent side), kill chain timing (bounded), the denunciation
    that arrives, and the deposit still holding parcel and lock after it.
  - Done: `pytest tests/orchestration -q` green AND full suite
    `pytest tests/ -q` still green (legacy untouched);
    `ruff check src/ tests/` clean.
  - Verify: now — read the e2e test top to bottom as the story of the
    foundations: every name reads as spoken (FreezeHandler,
    WorkerConnector, WorkerHandler verbs), no coined jargon.

## Notes
- The legacy machine (`spa/commander.py`, `spa/worker.py`,
  `channel/hub.py`) is NOT modified in this macro: the new subpackage
  grows beside it; cutover is Macro 4, removals are Macro 6.
- New tests are classified at birth as implementation tests
  (`tests/orchestration/`, own `__init__.py`) per the two-kinds rule:
  they photograph the new subsystem while it grows; contract tests get
  revisited at cutover (Macro 4/6).
- Language: code/comments/commits in English; no AI/LLM references in
  any persisted output (contractual); commits per house style, no
  co-author lines.
- Design authority order on any doubt: the interview register
  (F1-F39) > design v3 > this plan.
