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
- [ ] **Phase 2**: WorkerConnector — the per-WorkerHandler wire
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
    that WorkerHandler (identity by construction); handshake: child
    sends {pid, config echo} → reply carries {global_store, version}
    (F31: the store travels in the handshake, no disk); CALL/REPLY/EVENT
    framing reused from channel/frame.py — the hub
    (`channel/hub.py`) is NOT touched here (it dies in Macro 6);
    EOF/error on the stream = a LOCAL event surfaced to the owner via
    callback (burial on event, E13); the ChannelHub multi-member logic
    is not replicated: one connector, one stream.
  - Details: class WorkerConnector owned by the WorkerHandler
    (attribute `worker_handler.connector`): accept-side endpoint,
    handshake, call()/send_event()/reply routing, on_closed callback.
    Tests on a loopback UDS in a tmp dir: handshake payloads, call/reply
    round-trip, event delivery, EOF detection, stale-socket
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
  - Decisions: name = `<group_name>_<counter>` (`standard_0001`),
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
