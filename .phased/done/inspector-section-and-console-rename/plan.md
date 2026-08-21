# Context: wf/inspector-section-and-console-rename
Parent: main
Mode: autonomous

## Objective
Give the SPA pool a human-facing inspector: a new `_server/inspector` section
(mounted only when `GNR_ASGI_INSPECTOR` is set, no auth) serving an HTML page
that shows the commander's picture and every worker's registers in real time
over SSE, fed by observation events pushed worker → commander → browser.
Beforehand, rename the MCP eval door from the `inspect` family to the
`console` family so "inspector" names only the page.

## Work Plan

- [x] **Phase 1**: Rename the MCP eval door: inspect family → console family
  - Pattern reference: library-standard (mechanical rename, no new design)
  - Files: src/genro_asgi/applications/spa_inspector.py (git mv → spa_console.py),
    src/genro_asgi/spa/orchestration/spa_commander.py,
    src/genro_asgi/spa/orchestration/worker_handler.py,
    src/genro_asgi/spa/orchestration/spa_worker.py,
    tests/orchestration/test_orchestration_inspect.py (git mv → test_orchestration_console.py),
    plus any import site found by grepping `spa_inspector|SpaInspector|INSPECT_OP_PATH|inspect_target|inspect_expression` under src/ and tests/
  - Decisions (ratified 2026-08-21):
    - module `applications/spa_console.py`; classes `SpaConsole`,
      `SpaConsoleMcpApplication`; `mcp_name = "genro-spa-console"`
    - MCP tool `inspect` → `eval` (route method `eval` on `SpaConsole`;
      `targets` stays)
    - commander: property `inspect_targets` → `console_targets`;
      method `inspect_target(target, expr)` → `eval_in_target(target, expr)`
    - channel op: `INSPECT_OP_PATH = "/op/inspect"` → `EVAL_OP_PATH = "/op/eval"`
      (constant renamed in worker_handler.py and in its `__all__`)
    - worker: `inspect_expression` → `eval_expression`
    - NO backward-compatibility aliases (the only consumer is genropy-asgi,
      fixed in a follow-up outside this workflow — see Notes)
  - Details: git mv the module and the test file; apply the renames above;
    update docstrings that say "inspect"/"inspector" for the door (the word
    "inspector" must no longer appear in the console module — it now names the
    `_server/inspector` page only); update error messages that embed the old
    names. Do not touch CLAUDE.md (see Notes).
  - Done: `pytest tests/` passes; `ruff check src/` zero errors;
    `grep -rn "spa_inspector\|SpaInspector\|INSPECT_OP_PATH\|inspect_target\|inspect_expression" src/ tests/` returns nothing
  > Done: renames applied — `applications/spa_console.py` with `SpaConsole` /
  > `SpaConsoleMcpApplication` (`mcp_name = "genro-spa-console"`, MCP tool
  > `eval`), commander `console_targets` / `eval_in_target`,
  > `EVAL_OP_PATH = "/op/eval"`, worker `eval_expression`; no aliases left.
  > 2098 passed, 2 skipped; `ruff check src/ tests/` clean; the grep returns
  > nothing.
  > Files: src/genro_asgi/applications/spa_console.py (from spa_inspector.py),
  > src/genro_asgi/spa/orchestration/spa_commander.py,
  > src/genro_asgi/spa/orchestration/worker_handler.py,
  > src/genro_asgi/spa/orchestration/spa_worker.py,
  > tests/orchestration/test_orchestration_console.py (from
  > test_orchestration_inspect.py)

- [x] **Phase 2**: The census — structured JSON-safe read of the whole pool
  - Pattern reference: the eval op chain — `EVAL_OP_PATH` in
    src/genro_asgi/spa/orchestration/worker_handler.py, its dispatch in
    src/genro_asgi/spa/orchestration/spa_worker.py (`frame.path ==` branch
    around line 1541 pre-rename), and `SpaCommander.eval_in_target`
    (spa_commander.py, around line 832 pre-rename) for the commander→worker call
  - Files: src/genro_asgi/spa/orchestration/worker_handler.py,
    src/genro_asgi/spa/orchestration/spa_worker.py,
    src/genro_asgi/spa/orchestration/spa_commander.py,
    tests/orchestration/test_orchestration_census.py (new)
  - Decisions (ratified 2026-08-21):
    - name family: `census` — op `CENSUS_OP_PATH = "/op/census"`; worker method
      `census` (pure reading, no arguments, but it builds a fresh dict each
      call and is called over the channel: a plain method, not a property);
      commander method `get_pool_census()` (async — it calls every worker)
    - the census is JSON-safe by construction: only str/int/float/bool/None,
      dicts and lists; live stores and objects are never included, only their
      metadata fields and sizes
    - a worker that fails to answer appears in the census as
      `{"error": "<message>"}` under its name — the census never raises for
      one dead worker
  - Details: worker side — build a dict with: `user_register` /
    `connection_register` / `page_register` (per register: for each key from
    `keys()`, the item's JSON-safe metadata fields via `get(key)`; Register has
    NO `.items()` — surface is `keys()`, `get(key)`, `keys_by(field, value)`;
    skip any field holding a live object), `cid_connection_map`,
    `subscribed_tables`, `dbevent_deposit` (per table: queued count).
    Commander side — `get_pool_census()` returns: `user_map` (per user: group,
    frozen, on_hold, occupancy_percent, pending_dbevents, pending_datachanges),
    `connection_user_map`, `page_connection_map`, `counters`, `default_group`,
    per group in `group_map`: `user_worker_map`, `living_workers`, occupancy
    percent, worker cap, `worker_max_number`; `delivery_desk`:
    `subscribed_tables`, `event_max_age_seconds`, and the per-key queue LENGTHS
    of `page_dbevent_map`, `page_datachange_map`, `user_store_change_map`;
    plus `workers`: {worker_name: its census dict} gathered via
    `worker_handler.connector.call(CENSUS_OP_PATH, {})` for every living worker.
  - Done: `pytest tests/orchestration/test_orchestration_census.py` passes with
    tests asserting — on a local_worker pool with at least one user, one
    connection and one page — that the census contains that user under
    `user_map` and under the worker's `user_register`, that every leaf is
    JSON-serialisable (`json.dumps` succeeds on the whole census), and that a
    named unreachable worker yields the error entry instead of an exception;
    full `pytest tests/` green
  > Done: worker `census()` (JSON-safe projection of the three registers, the
  > cookie map, the subscribed tables and the per-table deposit counts) served
  > on `CENSUS_OP_PATH = "/op/census"`; commander `get_pool_census()` with the
  > routing maps, counters, delivery-desk queue lengths, per-group placements
  > and one census per living worker, a mute worker becoming
  > `{"error": ...}`. 4 new tests pass; full suite 2102 passed, 2 skipped;
  > `ruff check src/ tests/` clean.
  > Files: src/genro_asgi/spa/orchestration/worker_handler.py,
  > src/genro_asgi/spa/orchestration/spa_worker.py,
  > src/genro_asgi/spa/orchestration/spa_commander.py,
  > tests/orchestration/test_orchestration_census.py

- [x] **Phase 3**: Observation events — register changes pushed worker → commander → subscribers
  - Pattern reference: the child→parent lane — `store_get` in
    src/genro_asgi/spa/orchestration/spa_worker.py (around line 1353) and the
    lane CALL helper (around line 1607); the worker_events envelope slot —
    `_worker_events.append` (spa_worker.py around line 636),
    `ENVELOPE_SLOT_WORKER_EVENTS` unpacking in
    src/genro_asgi/spa/orchestration/envelope_handler.py (around line 146)
  - Files: src/genro_asgi/spa/orchestration/spa_worker.py,
    src/genro_asgi/spa/orchestration/worker_handler.py,
    src/genro_asgi/spa/orchestration/envelope_handler.py,
    src/genro_asgi/spa/orchestration/spa_commander.py,
    tests/orchestration/test_orchestration_observation.py (new)
  - Decisions (ratified 2026-08-21):
    - name family: `observation` — worker flag `observation_on`, switch op
      `OBSERVE_OP_PATH = "/op/observe"` (payload `{"on": bool}`), commander
      methods `subscribe_observation(queue)` / `unsubscribe_observation(queue)`
    - event shape: `{"kind": <str>, "source": <worker name or "commander">,
      "data": <JSON-safe dict>}`; kinds named after the mutation they report
      (e.g. `new_user`, `new_connection`, `new_page`, `drop_user`,
      `connection_user_changed`, `user_frozen`)
    - switch policy: the commander broadcasts `{"on": true}` to every living
      worker when the FIRST subscriber arrives and `{"on": false}` when the
      LAST one leaves; a worker spawned while observation is on receives the
      switch at REGISTER time
    - delivery is best-effort: a failed or dropped observation event is logged
      and forgotten — it must NEVER raise into the traffic path or block a
      mutation (this is a debug surface; the observer must not change what it
      observes)
    - commander-side mutations are relayed from the `on_*` handlers of
      envelope_handler.py (the single-writer choke point) — no new writer is
      introduced
  - Details: worker side — at every site that mutates `user_register`,
    `connection_register`, `page_register` or `cid_connection_map`, when
    `observation_on` is true, send the observation event up the lane
    (fire-and-forget: use the lane's EVENT frame if the worker connector
    exposes one; otherwise a CALL whose reply is awaited in a detached task —
    inspect worker_connector.py and pick the existing mechanism, never invent
    a new frame type). Commander side — an internal set of `asyncio.Queue`
    subscribers; `subscribe_observation` adds a queue (and turns workers on if
    it is the first), `unsubscribe_observation` removes it (and turns workers
    off if it was the last); every observation event arriving from a worker,
    and every commander-side `on_*` fold mutation while subscribers exist, is
    put on every queue with `put_nowait` (a full queue drops the event —
    best-effort).
  - Done: `pytest tests/orchestration/test_orchestration_observation.py`
    passes with tests asserting — on a local_worker pool — that after
    `subscribe_observation(queue)` a new connection produces at least one
    event on the queue with the right kind and source, that before any
    subscription the worker flag is off and no event flows, and that after
    `unsubscribe_observation` of the only queue the flag is off again;
    full `pytest tests/` green
  > Done: worker flag `observation_on` switched by `OBSERVE_OP_PATH =
  > "/op/observe"`, mutations reported from the single writer of the worker
  > events (`add_worker_event` → `report_observation`) as a detached CALL on
  > `DESK_OBSERVATION_PATH`, served by the desk's `op_observation`; commander
  > `subscribe_observation` / `unsubscribe_observation` / `switch_observation` /
  > `publish_observation` with `observation_watched`, the vertex fold relayed
  > from `CommanderEnvelopeHandler.__call__`, and a handler switching its
  > process on at its first envelope when somebody is already watching. All
  > delivery best-effort: put_nowait, failures logged and dropped.
  > 4 new tests pass; full suite 2106 passed, 2 skipped; `ruff check src/
  > tests/` clean.
  > Files: src/genro_asgi/spa/orchestration/spa_worker.py,
  > src/genro_asgi/spa/orchestration/worker_handler.py,
  > src/genro_asgi/spa/orchestration/envelope_handler.py,
  > src/genro_asgi/spa/orchestration/spa_commander.py,
  > tests/orchestration/test_orchestration_observation.py

- [x] **Phase 4**: The `_server/inspector` section — page route, census route, SSE stream
  - Pattern reference:
    src/genro_asgi/applications/server_sections/monitor_section.py (section
    shape, HTML served from resources/ — see its `read_text` at line 140,
    attach in server_app.py lines 138-141); `SseStream` in
    src/genro_asgi/sse.py:50 with its usage in
    src/genro_asgi/applications/mcp.py (the GET/SSE branch)
  - Files: src/genro_asgi/applications/server_sections/inspector_section.py (new),
    src/genro_asgi/applications/server_sections/__init__.py,
    src/genro_asgi/applications/server_app.py,
    tests/test_inspector_section.py (new, contract)
  - Decisions (ratified 2026-08-21):
    - section name `inspector`, attached in `ServerApplication.__init__` ONLY
      when `os.environ.get("GNR_ASGI_INSPECTOR")` is truthy (`import os` at
      file top); no `auth_rule` on any route — mounting is the gate, ratified:
      for now the inspector is NOT protected
    - routes: `page` (GET, `media_type="text/html"`, serves
      resources/inspector.html — Phase 5 writes the file; this phase ships a
      minimal placeholder with the structural container ids), `census` (GET,
      JSON: `get_pool_census()` of every mounted `SpaApplicationNew`, keyed by
      app code), `stream` (GET, SSE via SseStream: one `census` event with the
      full census on open, then every observation event; subscribes with
      `subscribe_observation` on open, unsubscribes on close)
    - SPA fronts discovered as in the console app: the server's applications
      filtered by `isinstance(mounted, SpaApplicationNew)` (see
      `SpaConsole.spa_fronts` post-rename)
    - the section NEVER touches the hosted site: no sticky_cid, no connection,
      no call into site paths — it reads commander surfaces and the census op
      only
  - Details: build the section as a `RoutingClass` with the application as
    parent (semantic name, per house rule); wire stream open/close to
    subscribe/unsubscribe so the worker switch follows the page's presence;
    attach conditionally in server_app.py next to the other attach_section
    calls; export from server_sections/__init__.py.
  - Done: `pytest tests/test_inspector_section.py` passes with contract tests
    asserting — via the test server harness — that WITHOUT the env var
    `_server/inspector/page` answers 404, that WITH the env var (monkeypatched)
    the page answers 200 text/html, `census` answers 200 application/json with
    a JSON body, and that no response carries a `sticky_cid` cookie;
    full `pytest tests/` green; `ruff check src/` zero errors
  > Done: `InspectorSection` with `page` (text/html, resources/inspector.html
  > placeholder carrying the five structural ids), `census` (JSON, one entry per
  > mounted `SpaApplicationNew`) and `stream` (SSE over `SseStream`, one
  > `census` event on open then every observation, subscribing and
  > unsubscribing with the reader); attached in `ServerApplication.__init__`
  > only when `GNR_ASGI_INSPECTOR` is set, no `auth_rule` anywhere. Needed one
  > seam outside the listed files: `RoutedApplication.__call__` now lets a
  > handler answering a `StreamingResponse` speak the wire itself (there was no
  > way to stream from a route). 5 contract tests pass; full suite 2111 passed,
  > 2 skipped; `ruff check src/ tests/` clean.
  > Files: src/genro_asgi/applications/server_sections/inspector_section.py,
  > src/genro_asgi/applications/server_sections/resources/inspector.html,
  > src/genro_asgi/applications/server_sections/__init__.py,
  > src/genro_asgi/applications/server_app.py,
  > src/genro_asgi/routed_application.py,
  > tests/test_inspector_section.py

- [x] **Phase 5**: The inspector page — HTML+JS, tree view, live updates, stop/resume
  - Pattern reference:
    src/genro_asgi/applications/server_sections/resources/monitor.html (page
    served from resources, same-origin fetch, no external assets)
  - Files: src/genro_asgi/applications/server_sections/resources/inspector.html (new),
    src/genro_asgi/applications/server_sections/inspector_section.py,
    tests/test_inspector_section.py
  - Decisions (ratified 2026-08-21):
    - layout (the owner's own): a top panel with the commander's information
      (counters, default_group, per-group occupancy/cap/worker_max_number,
      delivery desk summary: subscribed tables and queue totals); below it a
      grid with ONE ROW PER WORKER; each worker row a panel with a TREE
      user → connections → pages, plus its subscribed tables, dbevent deposit
      counts and queue lengths
    - update model: the page holds NO merge logic — any observation event
      arriving on the EventSource triggers a debounced (200 ms) refetch of
      `census` and a full re-render; a small event log panel shows the last
      50 raw events
    - controls: a stop/resume button (stop closes the EventSource and freezes
      the view; resume reopens it and refetches); the timestamp of the last
      reading always visible
    - zero external assets: all CSS and JS inline in inspector.html; plain
      fetch + EventSource, same origin, no CORS
  - Details: replace the Phase 4 placeholder with the real page; keep the JS
    small and dumb (render functions from the census JSON, no client-side
    state beyond the last census and the paused flag); ids on the structural
    containers (`commander-panel`, `worker-grid`, `event-log`, `last-read`,
    `toggle-stream`) so the contract test can assert them.
  - Done: the contract test asserts the served page contains the five
    structural ids above and references both `census` and `stream` route
    paths; full `pytest tests/` green
  - Verify: now — with a running pool (`GNR_ASGI_INSPECTOR=1`) open
    `/_server/inspector/page`, watch a login create its user row live, press
    stop, confirm the view freezes while the pool keeps moving, resume
  > Done: the real page replaces the placeholder — a commander section (one
  > card per SPA front: counters, default group, per-group
  > occupancy/cap/worker_max_number/placements, delivery-desk tables and queue
  > totals), a worker grid with one card per worker carrying the
  > user → connections → pages tree plus its subscribed tables, deposit counts
  > and cookie map, and an event log of the last 50 raw observation events.
  > No merge logic on the client: any observation event debounces (200 ms) a
  > refetch of `census` and a full re-render; stop closes the EventSource and
  > freezes the view, resume reopens and refetches; the last-read timestamp is
  > always visible. All CSS and JS inline, same-origin fetch + EventSource.
  > 6 contract tests pass (the new one asserts the five structural ids and both
  > sibling endpoints); full suite 2112 passed, 2 skipped; `ruff check src/
  > tests/` clean.
  > Files: src/genro_asgi/applications/server_sections/resources/inspector.html,
  > tests/test_inspector_section.py
  > Verify: now — the browser pass this unattended run cannot do: with a
  > running pool (`GNR_ASGI_INSPECTOR=1`) open `/_server/inspector/page`, watch
  > a login create its user row live, press stop, confirm the view freezes
  > while the pool keeps moving, then resume.

- [x] **Phase 6**: Coherence review and auto-fix (final, mandatory)
  - Pattern reference: same as Phases 1..5 (cross-check against them)
  - Files: only the files written by Phases 1..5 (collect them from their
    `Files:` fields). Never touch a pre-existing file they did not modify.
  - Decisions:
    - Auto-fix directly: tool-fixable lint (ruff), unused imports, formatting,
      trivially mechanical fixes. Re-run the tests after each non-tooling fix;
      if one breaks a test, roll back that fix and flag it instead.
    - Never auto-fix: logic errors, design divergences from the pattern
      reference, missing edge cases, anything architectural. Those go to
      `review.md` only.
  - Details: convergence loop (max 3 cycles) of linter scoped to the file set
    → auto-fix → linter → test suite; stop early if a cycle makes no progress.
    Then write `.phased/active/inspector-section-and-console-rename/review.md`
    with three sections: **Auto-fixed** (file, what, tool), **Flagged for
    human** (file, description, suggested action), **Final state** (linter
    output, suite result, files reviewed).
  - Done: `review.md` exists in the plan directory with the three sections,
    linter zero errors on the file set, full suite green
  > Done: `review.md` written with the three sections. One auto-fix, formatting:
  > the `__all__` of `server_sections/__init__.py` had grown to 133 characters
  > against the declared `line-length = 100`, invisible to ruff (`E501` is not in
  > its `select`) — wrapped one name per line. Seven items flagged for the human,
  > none of them a logic error or a divergence from a pattern reference: the
  > double `_census_field` evaluation (not fixed — the one-line fix needs a
  > walrus, an idiom absent from `src/`), the two sources publishing each
  > mutation, the `census` route contract-tested only empty,
  > `_observation_switched` never cleared, the redundant fetch on resume, the
  > stale CLAUDE.md overview and the genropy-asgi import follow-up. Convergence
  > in one cycle: lint clean → fix → lint clean → suite green. `ruff check src/
  > tests/` clean; full suite 2112 passed, 2 skipped.
  > Files: .phased/active/inspector-section-and-console-rename/review.md,
  > .phased/active/inspector-section-and-console-rename/notes.md,
  > src/genro_asgi/applications/server_sections/__init__.py

## Notes
- genropy-asgi imports `SpaInspectorMcpApplication` in
  `src/genropy_asgi/spa/config.py` (line 51, mount `_inspect` at line 92):
  after Phase 1 that repo needs a one-line follow-up (import +
  `mount="_console"`, `code="console"`). OUTSIDE this workflow, done by hand
  after finalize.
- CLAUDE.md carries uncommitted local edits on this machine: NO phase touches
  CLAUDE.md. The "How it works" overview update for the console rename and
  the inspector section is flagged in review.md as a human follow-up instead.
- The anomaly flags (same visitor twice, orphan page, dangling cookie) are
  deliberately OUT of scope — deferred to genropy/genro-asgi#32; the tree
  view makes them visible by structure.
- Non-negotiable (owner, 2026-08-21): the inspector never traverses the
  hosted site — its own mount, no sticky_cid minted, no connection opened.
  An observer that changes what it observes is useless during a collaudo.
- Configurable section auth tags and the plugin_config page are separate
  worksites: genropy/genro-asgi#30 and #31.

## Suggested execution config
| Phase | Effort | Model |
|-------|--------|-------|
| Phase 1 | low | opus |
| Phase 2 | medium | opus |
| Phase 3 | high | opus |
| Phase 4 | medium | opus |
| Phase 5 | medium | opus |
| Phase 6 | xhigh | opus |

## Quality check

> Quality check: 2026-08-21T20:01:46Z — commit 2cb90b9 — review panel, QA declined, findings 2 confirmed (1 fixed in 4ab02e2, 1 pre-existing and out of scope), 2 dismissed
