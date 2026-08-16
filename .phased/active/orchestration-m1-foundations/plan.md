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
  - Decisions: root `.genroasgi/freezed_users/<user>/` (folder name via
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
- [ ] **Phase 3**: WorkerHandler + LocalWorkerHandler
  - Run: opus / high
  - Pattern: `src/genro_asgi/spa/commander.py` spawn/kill machinery
    (`start_new_session=True`, `os.killpg`, the SIGTERM→SIGKILL
    escalation in `wait_workers_end`); config grammar:
    `src/genro_asgi/config/` existing builders
  - Files: src/genro_asgi/spa/orchestration/worker_handler.py,
    tests/orchestration/test_orchestration_worker_handler.py
  - Decisions: the three surfaces the wire asks of its handler, baptised by
    the owner on 2026-08-16 and already called by Phase 2 —
    `global_register_item_tytx` (property, the whole global store TYTX-encoded;
    born here with the PLACEHOLDER value `'not yet ready --- wait next phase'`
    and filled for real in Macro 3, when the commander that holds the master
    exists), `on_child_message(frame)` (an EVENT arrived from the child),
    `on_child_lost()` (the wire died on its own — where the burial starts);
    name = `<group_name>_<counter>` (`standard_0001`),
    counter resets at server restart (F39); spawn payload carries: the
    WorkerHandler name, the socket path, the DEPOSIT ADDRESS (never an
    object, E19), pool sizes, worker grammar; surveillance = LOW
    TOLERANCE (C2 full): mute probe → ONE repeat past the timeout →
    SIGKILL to the process group → await OS death → only then a
    successor — never two processes under one WorkerHandler (F22);
    bonifica = ONE mutator on the roster of its users: prune traces,
    discard parcels (folders) via FreezeHandler, remove semaphores
    ANNOUNCED by the dead holder (F12), all on the death EVENT (E13);
    governed deaths are the ones it ordered — everything else is wild
    (C3); photo annotation slot + cumulative counters (Prometheus
    sources, design §13.2); LocalWorkerHandler SUBCLASS: no probe, no
    SIGKILL, no relaunch, no self-defense — its health IS the server
    (F21); numbers (probe cadence, timeouts) in the config grammar.
  - Details: lifecycle: spawn → wait handshake (via WorkerConnector) →
    serving; kill chain; burial (socket unlink). Tests with a scripted
    fake child (a tiny python script): handshake happy path, mute-probe
    kill chain on a child that stops answering, wild-death bonifica
    hooks (roster callback + semaphore cleanup via FreezeHandler),
    LocalWorkerHandler exemptions.
  - Done: `pytest tests/orchestration -q` green; `ruff check src/ tests/`
    clean.
- [ ] **Phase 4**: Foundations end-to-end
  - Run: opus / high
  - Pattern: `src/genro_asgi/spa/worker_entry.py` (today's child
    bootstrap — orphan detection, entry wiring)
  - Files: tests/orchestration/child_stub.py,
    tests/orchestration/test_orchestration_foundations_e2e.py
  - Decisions: the stub is TEST-ONLY (the real worker process is
    Macro 2); it must exercise every foundation: connect + handshake
    (receives global store), answer probes, announce a lock take (EVENT
    frame), write a `connection_item` under the lock into the
    FreezeHandler root, release, then be killed via the WorkerHandler
    chain; after the wild kill the bonifica discards the user folder
    and any leftover lock.
  - Details: one e2e test telling the full foundations story on a real
    subprocess + real UDS in a tmp dir; assertions on: handshake
    payload, probe liveness, deposit contents at each step, kill chain
    timing (bounded), folder state after bonifica.
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
