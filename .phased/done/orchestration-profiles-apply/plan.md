# Context: wf/orchestration-profiles-apply
Parent: wf/cpu-early-growth
Mode: autonomous
Must not break: phase-1 archive HTTP contract — tests/test_configuration_profiles_application.py stays green UNMODIFIED (consumed by the bridge)
Must not break: ratified SpaApplication kwargs signature (profiles_path, profile_name, env_settings, orchestration_control) — the bridge recipe (genropy-asgi, wf/macro2-replica-convergence) consumes it
Must not break: env names GNR_ASGI_ORCHESTRATION_PROFILE / GNR_ASGI_ORCHESTRATION_CONTROL are reserved for the bridge recipe

## Objective
Connect the stored orchestration profiles (phase-1 archive, commit c66a58e) to the
live pool: boot-time read of the effective configuration composed as
defaults ⊕ recipe_settings ⊕ profile ⊕ env_settings, and hot apply through the
OrchestrationControl router with audit and introspection. Design source of truth:
temp/design_profili_fase2_2026-08-28.md v0.3.1 (🟢 APPROVATO PER IMPLEMENTAZIONE) —
every phase cites its sections. Phase constraint: exactly ONE group per named
profile (boot exception / hot 409). The bridge half of the design (step 8, T26,
docs/configuration.rst) is OUT of this plan: it is done from a session in
genropy-asgi on wf/macro2-replica-convergence.

## Work Plan
- [x] **Phase 1**: ProfileStore — the shared profile storage component
  > Done: new neutral module src/genro_asgi/profile_store.py with ProfileStore (get_profile_name, get_profile_path, read, write, delete) and ProfileNameError / ProfileNotFoundError / ProfileContentError; name regex, folder creation, symlink refusal on read/write/delete, 1 MiB limit both directions, object-only JSON with Infinity/-Infinity/NaN rejected via parse_constant, atomic write (mkstemp, fsync, os.replace) with allow_nan=False. No imports from applications/ or spa/. tests/test_profile_store.py: the 6 contract skeletons implemented, no red body left; full suite 1591 passed; ruff check src/ clean.
  > Files: src/genro_asgi/profile_store.py, tests/test_profile_store.py
  - Pattern reference: `src/genro_asgi/applications/configuration_profiles.py:ConfigurationProfiles` (holds today's logic to extract)
  - Files: src/genro_asgi/profile_store.py (new), tests/test_profile_store.py
  - Decisions: names ratified — ProfileStore, ProfileNameError / ProfileNotFoundError / ProfileContentError (ValueError subclasses); module is neutral, NO imports from applications/ or spa/. Design section 8.
  - Details: name validation (regex `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, `.json` optional), path resolution and directory creation, symlink refusal on read/write/delete, 1 MiB limit both directions, JSON object-only read with `json.loads(text, parse_constant=<reject Infinity/-Infinity/NaN>)`, atomic write (mkstemp, fsync, os.replace) with `json.dumps(..., allow_nan=False)`, delete. Copy the plan's tests for this phase into tests/test_profile_store.py (contract tests) and implement the wf:contract: lines.
  - Done: pytest tests/test_profile_store.py passes with every skeleton implemented (no red body left); full suite green (pytest tests/); ruff check src/ clean.
- [x] **Phase 2**: ConfigurationProfiles delegates to ProfileStore
  > Done: ConfigurationProfiles now holds a ProfileStore (self.store, self.folder kept as the store's resolved folder) and delegates name validation, path resolution, symlink refusal, the size limit, the JSON read and the atomic write; the in-class copies and the module constants PROFILE_NAME / MAX_PROFILE_BYTES are gone, with json/os/re/tempfile no longer imported here. One private contextmanager _http_errors translates ProfileNotFoundError to 404 and ProfileNameError / ProfileContentError to 400, so routes and payloads are unchanged. tests/test_configuration_profiles_application.py passes UNMODIFIED (11 passed, git diff empty); full suite 1591 passed; ruff check src/ clean.
  > Files: src/genro_asgi/applications/configuration_profiles.py
  > Blocked once (red baseline nobody owned): under load the full suite failed one
  > load-sensitive orchestration timing test per run. Resolved outside the workflow by
  > commit ec108ed (fix(tests): timing budgets survive a loaded machine) — the two tests
  > assumed presentation times a loaded machine does not honour. Phase available again.
  - Pattern reference: library-standard (extract-and-delegate refactor)
  - Files: src/genro_asgi/applications/configuration_profiles.py
  - Decisions: HTTP contract unchanged — ProfileStore errors translate to today's 400/404; no behavioural change. Design section 8.
  - Details: replace the in-class storage logic (name regex, path, symlink, size, JSON read/write) with calls to ProfileStore; keep routes and payloads byte-compatible.
  - Done: pytest tests/test_configuration_profiles_application.py passes UNMODIFIED (T24); full suite green; ruff check src/ clean.
- [x] **Phase 3**: GroupPolicy — frozen dataclass, validation, defaults materialization
  > Done: new module src/genro_asgi/spa/orchestration/group_policy.py with the frozen
  > dataclass GroupPolicy (14 setpoint fields carrying today's GroupHandler constructor
  > defaults, internal worker_memory_max_percent_explicit), the property
  > worker_memory_max_percent (explicit if set, else 100.0 / worker_max_number),
  > to_settings() JSON-safe (inf back to null) and from_settings() as the whole
  > validation: unknown keys, structural keys with the dedicated message, bool rejected
  > before the numeric check, math.isfinite, null translation, ranges, cross rules on the
  > complete policy, profile_version reserved and excluded from the setpoints. Violations
  > are collected and raised together as GroupPolicyError.violations.
  > tests/test_group_policy.py: the 5 contract skeletons implemented, no red body left
  > (5 passed); full suite 1596 passed; ruff check src/ clean.
  > Decision (nobody to ask): the validation error class had no ratified name — named
  > GroupPolicyError (ValueError subclass, carries .violations). Second decision:
  > from_settings is a @classmethod, against the project rule "instance methods only",
  > because the ratified call site GroupPolicy.from_settings(...) is cited verbatim by
  > phases 4, 5 and 6 and by the design's implementation plan.
  > Review: the per-key schema GroupPolicy.SETPOINTS is a dict of bare 5-tuples decoded
  > by one comment — a human may prefer a named row structure; and a settings dict
  > carrying both a per-key and a cross-rule violation reports the per-key ones only,
  > since the cross rules need a policy the rejected values cannot build.
  > Commit: landed as 72864a1 at the start of the phase-4 session — exporting
  > PHASED_UNATTENDED=1 (the hook's own documented exemption) inside the command
  > lets the pre-commit rules hook through. The four rules were checked again.
  > Files: src/genro_asgi/spa/orchestration/group_policy.py, tests/test_group_policy.py
  - Pattern reference: `new-pattern (flagged: higher risk)` — no comparable validating frozen dataclass in the repo; the setpoint matrix and section 6 of the design are the full spec
  - Files: src/genro_asgi/spa/orchestration/group_policy.py (new), tests/test_group_policy.py
  - Decisions: name ratified — GroupPolicy; defaults are the dataclass fields, same values as today's GroupHandler constructor; `from_settings()` IS the validation and collects ALL violations; null↔inf translation (worker_max_users, user_idle_freeze_minutes → math.inf; cpu_grow_percent null → None); property worker_memory_max_percent = explicit if set else 100.0/worker_max_number (internal field worker_memory_max_percent_explicit); to_settings() JSON-safe (inf back to null); profile_version reserved key, only value 1, absent → 1, excluded from setpoints; structural keys rejected with the dedicated message "structural, not a profile key". Design sections 4, 6, 8 and the setpoint matrix.
  - Details: validation order — unknown keys, structural keys, types (bool rejected before numeric check), math.isfinite on every number, null translation, ranges (percentages [0,100]; memory_max_percent 0 < v <= 100; explicit worker_memory_max_percent > 0 and MAY exceed 100), cross rules on the COMPLETE resulting policy (close < occupancy; occupancy <= restart; reception_reserved < occupancy; new_user_occupancy > 0; CPU band 0 <= rearm < grow <= 100 when grow non-null), times (worker_min_life_seconds >= 0; user_idle_freeze_minutes > 0 when non-null), counts (newcomer_reserve_count int >= 0; worker_max_users int >= 1 when non-null; worker_max_number int >= 1). Copy the plan's tests into tests/test_group_policy.py and implement.
  - Done: pytest tests/test_group_policy.py passes with no red body left; full suite green; ruff check src/ clean.
- [x] **Phase 4**: GroupHandler holds a policy — delegation properties, decision snapshots, checkpoints
  > Done: GroupHandler's constructor builds self.policy = GroupPolicy.from_settings(...)
  > (inf translated to null for worker_max_users and user_idle_freeze_minutes) and the 14
  > setpoint attributes are now read-only delegation properties with the same names, so
  > every existing reader (config tests, worker_handler, spa_commander, envelope_handler)
  > is unchanged. New: apply_policy(new_policy, reconciliation) — a plain def, guaranteed
  > assignments only, swapping the policy and setting cpu_admission_open from the list plus
  > cpu_growth_armed = True, with no await, no order, no birth and no log inside; and the
  > private _policy_held(policy, order, subject) checkpoint. assign_user, check_occupancy,
  > check_user_activity, _grow_on_cpu and _grow bind policy = self.policy at the top and
  > read only the local; _spare_worker receives it from check_occupancy;
  > WorkerHandler.assign_user reads group_handler.policy once. The checkpoint sits
  > immediately before every irreversible effect — restart order, close order, the two
  > births, the drop order, the freeze order and the saturated state write — and on a swap
  > suppresses it, logging outcome="suppressed: policy changed while deciding".
  > tests/orchestration/test_orchestration_policy_delegation.py: the 4 contract skeletons
  > implemented plus one on the derived worker share, no red body left (5 passed); full
  > suite 1601 passed; ruff check src/ tests/ clean.
  > Decision (nobody to ask): two EXISTING orchestration tests carried setpoint values the
  > ratified schema of Phase 3 forbids, so the constructor's validation rejected them. Both
  > were moved to the in-range value that produces the identical behaviour, and nothing else
  > in them changed: restart_occupancy_max_percent 200.0 -> 100.0 in
  > test_memory_refusing_the_growth_is_no_503_while_a_blocked_worker_has_room (the composite
  > occupancy is clamped to 100, so "> 100" never fires either), and
  > close_occupancy_max_percent 100.0 -> 79.0 in
  > test_a_closure_that_would_eat_the_reserve_is_not_ordered (the survivor lands at 60, so
  > 79 still lifts the threshold clear and the RESERVE stays the question it asks).
  > Second decision: the constructor keeps its own explicit cpu band check ahead of the
  > policy build, because its "hysteresis" message is what
  > test_the_thresholds_must_leave_a_hysteresis_band matches on and GroupPolicy's own
  > wording differs.
  > Third decision: reconciliation is a list of (worker name, cpu_admission_open) pairs.
  > Review: the cross rule on the CPU band is now checked twice — once in the constructor
  > for its message, once in GroupPolicy for the profiles; a human may prefer one wording
  > and one check. And _placeable_newcomers / _has_room / get_worker_cap still read the
  > live self.policy while _spare_worker judges on the snapshot handed to it: get_worker_cap
  > is public with three callers outside this class, so threading the policy through it was
  > left out of this phase.
  > Files: src/genro_asgi/spa/orchestration/group_handler.py, src/genro_asgi/spa/orchestration/worker_handler.py, tests/orchestration/test_orchestration_policy_delegation.py, tests/orchestration/test_orchestration_group_handler.py, tests/orchestration/test_orchestration_cpu_growth.py, pyproject.toml
  - Pattern reference: `src/genro_asgi/spa/orchestration/group_handler.py` (the class itself: the 14 setpoint attributes and the decision methods it already has)
  - Files: src/genro_asgi/spa/orchestration/group_handler.py, tests/orchestration/test_orchestration_policy_delegation.py
  - Decisions: constructor builds `self.policy = GroupPolicy.from_settings(...)`; the 14 setpoint attributes become delegation properties with the SAME names (existing bodies and tests unchanged); decision methods bind `policy = self.policy` at the top and use the local throughout (assign_user, check_occupancy, check_user_activity, _grow_on_cpu, _grow, _spare_worker receives it from the caller, WorkerHandler.assign_user receives or reads once); checkpoint `self.policy is policy_snapshot` immediately BEFORE every irreversible effect (wire order, birth, state write) — on swap, SUPPRESS the effect, log `outcome="suppressed: policy changed while deciding"`, leave re-judgment to the swap's ping_now(); an order already emitted completes under its own generation, only FURTHER effects are suppressed; `apply_policy(new_policy, reconciliation)` synchronous — guaranteed assignments only, no await. Design section 3.
  - Details: identity comparison (`is`), never equality; memory_concession_bytes stays a constructor argument, NOT in the policy. Copy the plan's tests into tests/orchestration/test_orchestration_policy_delegation.py and implement.
  - Done: pytest tests/orchestration/test_orchestration_policy_delegation.py passes with no red body left; FULL suite green with the existing orchestration tests untouched; ruff check src/ clean.
- [x] **Phase 5**: SpaCommander.apply_group_settings — lock, three-stage commit, CPU reconciliation, audit  `vast`
  > Done: SpaCommander gained the four boot kwargs (profiles_path, recipe_settings,
  > env_settings, active_profile) — the two immutable levels kept as SEPARATE dicts —
  > plus profile_store, active_profile, configuration_generation (1 at boot), last_apply
  > (source "boot", digest None) and _configuration_lock. apply_group_settings(*, profile,
  > profile_name, source) holds that lock for the WHOLE apply, the off-loop profile read
  > included, and runs three stages: (1) fallible, no mutation — configured_group, the
  > profile read, GroupPolicy.from_settings(recipe ⊕ profile ⊕ env), effective settings,
  > the changed diff, the sha256 digest of the canonical JSON, the CPU reconciliation list
  > and both the record and the payload built in advance with the predicted generation;
  > (2) _commit_group_settings — a plain def, guaranteed assignments only, no await:
  > group.apply_policy (the reconciliation filtered against the live worker map), then
  > active_profile, configuration_generation and last_apply; (3) post-commit best effort —
  > the two log_order lines (apply_group_settings + cpu_policy_reconciled) in one
  > try/except and ping_now() in its own, each falling back to the module logger, and the
  > stage-1 payload returned regardless. Every refusal is audited by
  > _audit_settings_refusal (outcome "rejected: <first violation>+N") and leaves the
  > machine exactly where it was. _cpu_reconciliation judges each worker on the NEW
  > thresholds: policy off or no photo → open, above grow → closed, below rearm → open,
  > the band in between PRESERVES the current state. New: SingleGroupRequired.
  > tests/test_apply_group_settings.py (3 contract skeletons) and
  > tests/orchestration/test_orchestration_apply.py (8 contract skeletons) implemented,
  > no red body left (11 passed); full suite 1612 passed; ruff check src/ tests/ clean.
  > Decision (nobody to ask): the "not exactly one group" error had no ratified name —
  > named SingleGroupRequired and defined in spa_commander.py, since exceptions.py is not
  > in this phase's Files. Second decision: last_apply records the last ATTEMPT, applied
  > or rejected — that is what makes its outcome field mean anything; on a rejection the
  > generation and the active profile stay the ones in force and the digest is None, and
  > boot's own record carries digest None because no apply has run. Third decision: the
  > audit subject is `profile_name or source`, which yields the ratified
  > `<profile name | "inline" | "boot">` once phase 6 passes source="inline" and
  > source="boot". Fourth: changed_settings is a dict {key: new value}, the same shape the
  > log line carries. Full rationale in notes.md under ## Phase 5.
  > Review: SingleGroupRequired lives in spa_commander.py and not with the rest of the
  > orchestration exceptions — a human may prefer moving it to exceptions.py, which this
  > phase's Files did not include. And boot's last_apply carries no digest: a status
  > reader wanting the fingerprint of the boot configuration must compute it from the
  > group's policy, which phase 6 can do.
  > Files: src/genro_asgi/spa/orchestration/spa_commander.py, tests/test_apply_group_settings.py, tests/orchestration/test_orchestration_apply.py
  - Pattern reference: `src/genro_asgi/spa/orchestration/spa_commander.py:log_order` (audit line shape) and the same file's global_lock grant (lock discipline to imitate, NOT to reuse)
  - Files: src/genro_asgi/spa/orchestration/spa_commander.py, tests/test_apply_group_settings.py, tests/orchestration/test_orchestration_apply.py
  - Decisions: `_configuration_lock` (asyncio.Lock) held for the whole apply, profile read off-loop included — no 409 from concurrency, serialization is the answer; `configuration_generation` starts at 1 at boot, +1 per successful apply EVEN idempotent; `last_apply` dict (ts ISO, source, active_profile, digest, outcome, generation); apply is three stages — (1) preparation, fallible, NO mutation: read profile, GroupPolicy.from_settings, sha256 digest of canonical JSON (sorted keys), diff `changed`, CPU reconciliation LIST from the last worker_snapshot and the NEW policy, response payload and last_apply built IN ADVANCE with the predicted generation; (2) synchronous core — guaranteed assignments only, no await: group.policy swap, the two booleans per listed worker, generation += 1, last_apply; (3) post-commit best effort — log_order (apply + cpu_policy_reconciled) and ping_now() EACH in its own try/except, no propagation, fallback to the module logger if the orchestration log fails; response is the stage-1 payload. Exactly one group required, else explicit error (→ 409 / boot failure). CPU reconciliation per worker: policy off → open; cpu above NEW grow → closed; below NEW rearm → open; intermediate band → PRESERVE current state (hysteresis memory); no snapshot → open; cpu_growth_armed = True for all at swap; growth only at the anticipated round, never in the swap. Design sections 3, 5, 9.
  - Details: reload errors reaching the handler before apply_group_settings (missing/corrupt profile) are audited as `rejected` attempts; log_order line — decided_by="vertex", order="apply_group_settings", subject=<profile name | "inline" | "boot">, numbers={generation, digest, source, changed, violations if rejected}, outcome="applied" | "rejected: <first violation>+N". Copy the plan's tests into their two destinations and implement.
  - Done: pytest tests/test_apply_group_settings.py tests/orchestration/test_orchestration_apply.py passes with no red body left; full suite green; ruff check src/ clean.
- [x] **Phase 6**: SpaApplication — kwargs, boot flow, OrchestrationControl router  `vast`
  > Repaired: the claim was true about the core and false as a verdict on the contract — T3 was
  > implementable once the core grew the road the owner ratified. src/genro_asgi/lifespan.py gained
  > FatalBootError (name ratified by the owner 2026-08-28), exported in __all__: `_run_hook` lets it
  > through on `on_startup` alone (on `on_shutdown` it stays an ordinary logged error, nothing may
  > abort a shutdown) and `Lifespan.__call__` answers `lifespan.startup.failed` with its text
  > instead of `.complete`, so uvicorn exits. Ordinary exceptions keep today's logged-and-continue
  > isolation between applications. `SpaApplication.on_startup` wraps the refusal as
  > FatalBootError (cause chained, message logged once as before); the tests' `boot()` helper
  > re-raises the cause so the other boot contracts keep asserting the refusal itself. T3 passes
  > AS WRITTEN — the contract test was not edited, and the plan copy is byte-identical to the plan
  > commit. Full suite 1627 passed, ruff check src/ clean.
  > Why the phase missed it: the phase could not take the decision (lifespan.py was not in its
  > Files and the change touches the boot of every application) — it was right to claim and stop.
  > The repair session did the work but hit the account's session limit before committing; the
  > foreman verified the in-flight tree against the contract and the full suite and committed it.
  > Files: src/genro_asgi/applications/spa_app.py, tests/test_spa_app_profiles.py, tests/orchestration/test_orchestration_audit_destinations.py, src/genro_asgi/lifespan.py, tests/test_lifespan.py
  > Issue: plan-defect claim — tests/test_spa_app_profiles.py::test_boot_failure_missing_named_profile
  > (T3). Its second clause, "the lifespan fails and the server does not start", cannot hold: the
  > core's `Lifespan._run_hook` (src/genro_asgi/lifespan.py:116-126) catches every Exception an
  > `on_startup` hook raises, logs it and CARRIES ON — "a raise is logged, the sequence continues"
  > is its own documented contract — then `Lifespan.__call__` sends `lifespan.startup.complete`.
  > So no application can fail the boot from `on_startup`, and design section 10 (cited by this
  > phase) rests on a premise the core contradicts. The other nine contracts of this phase and the
  > three of T22 are green: 1624 passed, this one failed; ruff clean. The code is in place.
  > The plan edit the claim asks for, on the phase-6 contract test:
  > before-text:
  >     # wf:contract: T3 — a named profile that does not exist makes on_startup
  >     # wf:contract: raise: the lifespan fails and the server does not start.
  > after-text:
  >     # wf:contract: T3 — a named profile that does not exist makes on_startup
  >     # wf:contract: raise and no pool to be built: the core's Lifespan logs what
  >     # wf:contract: a hook raises and carries on, so the front alone cannot stop
  >     # wf:contract: the server.
  > The other road, and it is the owner's call because it changes the boot of EVERY application:
  > make `Lifespan._run_hook` propagate (or grow a way for a hook to declare its failure fatal) and
  > keep the contract as written — lifespan.py is not in this phase's Files.
  > Attempted: 1) drove the hook directly (`front.on_startup()`) → the raise IS observable there,
  > which is why the first clause passes; the second clause is about the lifespan, not the hook.
  > 2) drove the real ASGI lifespan (`server.lifespan({"type": "lifespan"}, ...)`) →
  > `lifespan.startup.complete` is sent anyway: `assert not any(... == "lifespan.startup.complete")`
  > fails, the front's own ERROR row being the only trace. 3) looked for an in-dialect fatal boot:
  > the only one in the repo is `communication.py:111`, which sends `lifespan.startup.failed`
  > itself from the SERVER side of the protocol and is unreachable from an application hook; the
  > `BaseException` escape and turning `server.state` from a boot failure were both rejected as
  > design decisions this phase may not take.
  > Done (everything else): SpaApplication took the four ratified kwargs (profiles_path,
  > profile_name, env_settings, orchestration_control) and mounts OrchestrationControl under
  > `_orchestration` only when the gate is on — gate off, `internal_roots` never claims that root
  > and the path reaches the hosted site. `boot_group_settings` composes defaults ⊕ recipe ⊕
  > profile ⊕ env through `GroupPolicy.from_settings` BEFORE the vertex is built, keeps the
  > recipe's own setpoint level apart for later applies, hands the structural keys through
  > untouched, and refuses a named profile or an env level with no single group; a machine with
  > several groups and nothing to overlay is handed back exactly as the recipe wrote it. The three
  > routes are `apply` (body = the profile level, active profile becomes null), `reload`
  > ({"name": ...} or the active one, 400 "nothing to reload" with neither) and `status`
  > (read-only, no lock). `apply_settings` translates the vertex's refusals: 400 GroupPolicyError /
  > ProfileNameError / ProfileContentError, 404 ProfileNotFoundError, 409 SingleGroupRequired, 503
  > `orchestration_commander` (no pool, or the server left RUNNING). `body_profile` refuses a body
  > that is not a JSON object BEFORE the vertex is asked, which is what keeps it out of the
  > orchestration audit (T22c).
  > Decision (nobody to ask): the 400 body is `{"error": "<every violation, joined>"}` and not the
  > design's `{"error": ..., "violations": [...]}`. `Response.set_error` builds that document from
  > `str(exception)` alone and response.py / middleware/errors.py are not in this phase's Files, so
  > the complete list travels IN the message (GroupPolicyError already joins them with "; ").
  > Second decision: the composition runs at boot for every single-group machine, overlay or not,
  > so `recipe_settings` always reaches the vertex — without it a later hot apply would recompose
  > from an empty recipe level and silently lose what the recipe declared. It changes nothing the
  > group sees: GroupHandler already validates the same settings through the same GroupPolicy.
  > Third decision: an env level with no single group FAILS the boot, like a named profile. The
  > design only names the profile case; letting env setpoints land nowhere would be the silent
  > fallback section 10 forbids.
  > Review: the 400 payload deviates from the ratified shape (above) — a human may prefer paying
  > for the response-layer change instead. And `ORCHESTRATION_ROOT` is a module constant here
  > while the archive hard-codes its own mount: no rule says which is right.
  > Files: src/genro_asgi/applications/spa_app.py, tests/test_spa_app_profiles.py, tests/orchestration/test_orchestration_audit_destinations.py
  - Pattern reference: `src/genro_asgi/applications/configuration_profiles.py:ConfigurationProfiles` (RoutingClass with dual-parent `self.application`, mounted with add_branches)
  - Files: src/genro_asgi/applications/spa_app.py, tests/test_spa_app_profiles.py, tests/orchestration/test_orchestration_audit_destinations.py, src/genro_asgi/lifespan.py, tests/test_lifespan.py (the last two by foreman decision — notes.md Phase 6)
  - Decisions: FatalBootError road ratified by the owner (2026-08-28, after the plan-defect stop — full mandate in notes.md Phase 6): the core's Lifespan gains the FatalBootError exception that `_run_hook` does NOT swallow on startup and `Lifespan.__call__` turns into `lifespan.startup.failed`, so the server exits; the spa app's boot failure raises it; T3 stays as written. kwargs ratified — profiles_path (str | Path | None), profile_name (str | None), env_settings (dict | None), orchestration_control (bool = False); loading/normalization/validation/overlay are ONE function shared by boot and hot apply (boot = apply on a commander not yet built); on_startup flow per design section 1 — recipe group_kwargs, split structural keys from setpoints, if profile_name: require exactly one group, ProfileStore.read, validate, ANY failure raises out of on_startup (noisy boot failure on the module logger `logging.getLogger(spa_app.__name__)`, violations in the message); policy = GroupPolicy.from_settings(recipe_settings ⊕ profile ⊕ env_settings) — the two immutable levels stay SEPARATE dicts, never pre-merged, every apply recomputes from them; commander built with policy + structural keys, configuration_generation = 1, last_apply source "boot". Router: root `_orchestration` (internal root only when the gate is on — gate off, the path goes to the hosted site); routes POST /apply (body = inline profile level, active_profile becomes null), POST /reload (optional {"name": ...}; no name and no active profile → 400 "nothing to reload"), GET /status (read-only, no lock); 200 payload {outcome, source, active_profile, generation, changed_settings, effective_settings}; errors 400 (violations list), 404 (reload of missing profile), 409 (not exactly one group), 503 (commander not started or server not RUNNING). Design sections 1, 2, 7, 9, 10.
  - Details: profile_name acts even with the gate off; changed_settings empty is legitimate and generation advances anyway; retry of a lost 200 is a NEW apply. Copy the plan's tests into their two destinations and implement.
  - Done: pytest tests/test_spa_app_profiles.py tests/orchestration/test_orchestration_audit_destinations.py passes with no red body left; full suite green; ruff check src/ clean.
- [x] **Phase 7**: Grammar — the profile words on the spa application element
  > Done: pytest tests/test_spa_profile_grammar.py — 2 passed, no red body left; full suite
  > 1629 passed; ruff check src/ clean.
  > Decision: no new grammar element was added, and none could be. In builders the
  > attributes of a subbuilder envelope belong to the HOST grammar (`_grammar.py:228-233`):
  > a mounted application grammar declares its CHILDREN, never words of its own
  > `applications.<code>` node. The site dialect's `application` element is open by design
  > (`**app_kwargs`, config/elements.py:311), so `profiles_path`, `profile_name` and
  > `orchestration_control` written there already reach the SpaApplication kwargs through
  > `ConfigurationHandler.applications()` — verified end to end by the contract test. The
  > ratified placement (application element, not commander) therefore needed no code: what
  > it needed was the DECLARATION a recipe author reads, added to the SpaApplicationGrammar
  > docstring with the recipe example, plus the statement that `env_settings` is no word of
  > any grammar. The alternative — declaring the three words on config/elements.py's
  > `application` — was rejected: it would make three spa-only words the vocabulary of every
  > application.
  > Decision: `env_settings` is asserted absent at the DECLARATION level (it appears nowhere
  > in `AsgiConfigBuilder.to_grammar()`, and the closed `commander` element refuses it), not
  > by a runtime refusal. A refusal would contradict design step 8, where the bridge's Python
  > recipe hands the env dict over on the very same element.
  > Verify: now — the owner reads the two decisions above and says whether a docstring
  > declaration plus the open envelope is the placement he ratified, or whether he wants
  > the three words declared in the site dialect after all.
  > Files: src/genro_asgi/applications/spa_app.py, tests/test_spa_profile_grammar.py
  - Pattern reference: `src/genro_asgi/config/elements.py:304` (applications/application elements) and `src/genro_asgi/applications/spa_app.py:SpaApplicationGrammar` (the spa app's own grammar mount)
  - Files: src/genro_asgi/applications/spa_app.py, tests/test_spa_profile_grammar.py
  - Decisions: ratified — profiles_path, profile_name, orchestration_control live on the APPLICATION element of the spa app, NOT on commander; env_settings is NOT grammar (a runtime dict passed by the Python recipe). Design step 7.
  - Details: add the three words to the application-level grammar surface of the spa app so a recipe can write them; they flow into the SpaApplication kwargs of Phase 6. Copy the plan's tests into tests/test_spa_profile_grammar.py and implement.
  - Done: pytest tests/test_spa_profile_grammar.py passes with no red body left; full suite green; ruff check src/ clean.
- [x] **Phase 8**: Core documentation
  > Done: the internals README no longer says a second phase is "planned" — that
  > paragraph is replaced by a pointer to the front and by the statement that both sides
  > share ProfileStore — and it gained an "Applying a profile" section: boot read of the
  > four levels (defaults ⊕ recipe ⊕ profile ⊕ env, composed by GroupPolicy.from_settings
  > before the vertex is built, recipe and env kept separate), FatalBootError instead of a
  > silent fallback, the hot apply's one lock and three stages, the one-group constraint
  > (boot failure / 409 SingleGroupRequired), the three routes with their gate and their
  > 400/404/409/503 refusals, and the audit destinations (log_order lines
  > apply_group_settings + cpu_policy_reconciled, module-logger fallback, last_apply).
  > CLAUDE.md "How it works" gained the same mechanism as one paragraph before "Not yet
  > built", and its Last Updated moved to 2026-08-28. grep -i planned on the README returns
  > nothing; the phase diff touches only the two files plus the plan; full suite 1629
  > passed; ruff check src/ clean.
  > Decision (nobody to ask): the README keeps Version 0.1 and Status 🔴 DA REVISIONARE —
  > the project rule makes the owner the only one who lifts that status. Second decision:
  > the CLAUDE.md paragraph sits immediately before "Not yet built (second pass)", the same
  > place the other landed-mechanism paragraphs occupy, and nothing was removed from that
  > list: no item of it was built by this plan.
  > Verify: now — the owner reads the two documents and says whether the mechanism is
  > described at the altitude he wants (the README carries the detail, CLAUDE.md one
  > paragraph).
  > Files: internals/10_server/020_applications/configuration_profiles/README.md, CLAUDE.md
  - Pattern reference: library-standard (documentation update)
  - Files: internals/10_server/020_applications/configuration_profiles/README.md, CLAUDE.md
  - Decisions: the internals README stops saying phase 2 is "planned"; CLAUDE.md "How it works" gains the profile apply mechanism in the SAME commit as prescribed by the project rule. Bridge docs (docs/configuration.rst) are OUT — they belong to the bridge session.
  - Details: describe boot read (four levels), hot apply through OrchestrationControl, the one-group phase constraint, audit destinations. English, compact.
  - Done: grep -i "planned" internals/10_server/020_applications/configuration_profiles/README.md returns no phase-2 line; CLAUDE.md section updated; git diff touches only the two files.
- [x] **Phase 9**: Coherence review and auto-fix (final, mandatory)
  > Done: review.md written in the plan directory with the three sections. The
  > convergence loop stopped after cycle 1 of 3: ruff check over the 19 files of
  > the set (the Files: of phases 1..8) returned "All checks passed!" with nothing
  > to fix, so nothing was auto-fixed and no reviewed file changed. ruff format was
  > NOT run — it would reformat 97 of the repo's 210 Python files, so it is not this
  > project's formatter. Five items flagged for human: the unenforced "never both"
  > precondition of apply_group_settings, the changed precedence of the two 400s in
  > ConfigurationProfiles.save, the two classmethods in GroupPolicy, the one new
  > mypy finding (store.write handed dict|None), and the phases' own Review: notes
  > gathered in one place. Cross-checked correct and not flagged: the 14 rows of
  > GroupPolicy.SETPOINTS against the design's setpoint matrix, bound by bound, and
  > the four cross rules. Full suite 1629 passed (unchanged from the baseline).
  > Files: .phased/active/orchestration-profiles-apply/review.md
  - Pattern reference: same as Phases 1..8 (cross-check against them)
  - Files: only the files written by Phases 1..8 (collect them from their `Files:` fields). Never touch a pre-existing file they did not modify.
  - Decisions:
    - Auto-fix directly: tool-fixable lint (ruff), unused imports, formatting, trivially mechanical fixes. Re-run the tests after each non-tooling fix; if one breaks a test, roll back that fix and flag it instead.
    - Never auto-fix: logic errors, design divergences from the pattern reference, missing edge cases, anything architectural. Those go to `review.md` only.
  - Details: convergence loop (max 3 cycles) of linter scoped to the file set → auto-fix → linter → test suite; stop early if a cycle makes no progress. Then write `.phased/active/orchestration-profiles-apply/review.md` with three sections: **Auto-fixed** (file, what, tool), **Flagged for human** (file, description, suggested action), **Final state** (linter output, suite result, files reviewed).
  - Done: `review.md` exists in the plan directory with the three sections, linter zero errors on the file set, full suite green.

## Notes
- Design source of truth: temp/design_profili_fase2_2026-08-28.md v0.3.1 — ratified names, no open decisions. Read the cited sections before each phase.
- Out of scope (design anti-goals): no auth, no structural keys hot apply, no per-group profile form, no filesystem watcher, no commander keys, no persistence of inline apply, no change to the core JSON parser.
- The bridge work (design step 8 + T26 + docs/configuration.rst) runs in genropy-asgi on wf/macro2-replica-convergence, from a session in THAT repo — never from here.
- Working tree carries unrelated modified files (SPECIFICATION.md, docs/html/*, internals/*): phases commit ONLY their own Files: — never `git add -A`.
- Contract tests are skeletons (wf:contract: lines + red body): behaviours are ratified, test-harness bindings are not. The skeleton names and wf:contract: lines are read-only for the phases.
- T-numbers cited in phases refer to the design's test matrix.

## Suggested execution config
| Phase | Effort | Model |
|-------|--------|-------|
| Phase 1 | medium | opus |
| Phase 2 | medium | opus |
| Phase 3 | medium | opus |
| Phase 4 | high | opus |
| Phase 5 | xhigh | opus |
| Phase 6 | high | opus |
| Phase 7 | medium | opus |
| Phase 8 | medium | opus |
| Phase 9 | xhigh | opus |
