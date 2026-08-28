# Notes — orchestration-profiles-apply

Imported from temp/design_profili_fase2_2026-08-28.md v0.3.1 (🟢 APPROVATO PER
IMPLEMENTAZIONE) by /import-workflow on 2026-08-28. The design document stays
the source of truth for rationale; T-numbers in the plan cite its test matrix.

Negative-assertion sweep (plan authoring, 2026-08-28): checked every
prohibition in the contract skeletons against the Decisions/Done of the other
phases — structural-key rejection (phase 3) vs the SpaApplication kwargs
(phase 6) and the grammar words (phase 7) do not collide (kwargs are not
profile keys); T8 generation-still vs T27 generation-advances do not collide
(rejected vs applied); T22c parser-400 exclusion vs T21 every-handler-attempt
do not collide (the parser rejection never reaches the handler). No defect.

## Phase 1
- `ProfileStore` exposes name and path as two methods (`get_profile_name`,
  `get_profile_path`) instead of one tuple-returning resolver: the archive of
  Phase 2 needs the validated name and the filename separately, and a method
  named for a path that returns a pair reads wrong.
- `read()` raises `ProfileContentError` for a symlink (not a name error), so
  Phase 2 keeps translating symlinks to today's 400 and absence to 404.
- The non-finite `parse_constant` callback raises `ProfileContentError`
  directly; it is not caught by the `JSONDecodeError` handler, so the literal
  name reaches the caller in the message.
- The working tree carried the owner's uncommitted documentation edits
  (SPECIFICATION.md, docs/html/, internals/) before this run: the phase commit
  lists its own paths explicitly instead of `git add -A`.

## Phase 2
- ConfigurationProfiles keeps `self.folder`: the archive lists the directory itself
  (`profiles` route) and a contract test asserts `app.profile_store.folder`. It is now
  the store's already resolved folder, not a second resolution.
- Error translation lives in one private contextmanager rather than a try/except per
  route: three routes needed the identical 404/400 mapping.
- ProfileStore.write validates the body type itself, so the route no longer pre-checks
  `body_data`; the answer stays 400 with the same message.

## Phase 4

- The 14 setpoints are stored ONLY in `self.policy`; the same-named attributes became
  read-only properties. Chosen over keeping shadow attributes in sync because a swap
  must be one assignment, and because every existing reader (`test_config`,
  `worker_handler.assign_user`, `spa_commander` monitor, `envelope_handler`) keeps
  working untouched.
- `get_worker_cap` was NOT given a policy parameter: it is public and called from
  `worker_handler.py:344` and `spa_commander.py:1020` with one argument. The same
  reasoning stopped the threading at `_placeable_newcomers` and `_has_room`, which
  call it. They are synchronous, so no swap can land inside them — only a decision
  spanning an await can see two policies, and that is what the snapshot covers.
- The checkpoint before `restart_worker` cannot currently fail (no await precedes it
  in `check_occupancy`). It was written anyway, so the rule reads uniformly and an
  await added above it later does not silently break the contract.
- `reconciliation` is a list of pairs rather than a dict: the plan's Phase 5 calls it
  a LIST, and the order is the caller's.

## Phase 5

Choices the plan left open, decided here (no chat to ask):

- **Signature**: `apply_group_settings(*, profile=None, profile_name=None, source="inline")`.
  `profile` is the inline level (the active profile becomes None), `profile_name` is the
  stored one (it becomes the active profile). The audit `subject` is `profile_name or
  source`, which produces exactly the ratified set `<profile name | "inline" | "boot">`
  once Phase 6 passes `source="inline"` for POST /apply and `source="boot"` at boot.
- **Where the immutable levels live**: on the vertex, as `recipe_settings` and
  `env_settings`, two separate dicts never merged into one another, plus `profiles_path`
  and `active_profile` — four new constructor kwargs. Phase 5's `Files:` allowed only
  `spa_commander.py`, and every apply must recompose from the levels, so the vertex is
  where they had to go.
- **`SingleGroupRequired`** — the "not exactly one group" error had no ratified name.
  Defined in `spa_commander.py` beside the commander that raises it, NOT in
  `exceptions.py`, which Phase 5's `Files:` does not include.
- **`last_apply` is the last ATTEMPT**, applied or rejected. Its `outcome` field only
  earns its place that way. On a rejection the generation and the active profile stay
  the ones in force and there is no digest — no new configuration exists. Boot's record
  carries `digest: None` for the same reason: no apply has run.
- **`changed_settings` is a dict** `{key: new value}`, the same shape the audit line
  carries as `numbers={"changed": ...}` — one shape, not two.
- **`effective_settings` is `new_policy.to_settings()`**, so the payload always survives
  `json.dumps(..., allow_nan=False)`.
- **Stage two filters the reconciliation against the live worker map.** Stage one awaits
  (the profile is read off the loop), so a worker can be closed in between; without the
  filter `apply_policy` would raise KeyError AFTER swapping the policy — the half-applied
  state the three stages exist to make impossible.
- **`profile_name` with no profiles folder raises `ProfileNotFoundError`** instead of an
  AttributeError on None: Phase 6 maps it to the 404 a reload of a missing profile gets.

## Phase 6

Choices the plan did not settle, and why.

**The 400 body.** The design ratifies `{"error": ..., "violations": [...]}`.
The core builds an error document in exactly one place — `Response.set_error`,
`{"error": str(exception)}` — and `middleware/errors.py` is what calls it. A
handler has no way to set a status and a body of its own: the dispatcher passes
its return value to `set_result`, which never touches the status. Both files sit
outside this phase's `Files:`, and phase 5 set the precedent of staying inside it
(`SingleGroupRequired` lives in spa_commander.py for the same reason). So the
violations travel inside the message, where `GroupPolicyError.__str__` already
joins them with "; ". The alternative costs a response-layer change that every
error document in the core would inherit.

**Composing at boot even with no overlay.** `boot_group_settings` runs for every
single-group machine, not only when a profile or an env level is present, because
`recipe_settings` has to reach the vertex either way: a later hot apply recomposes
`recipe ⊕ profile ⊕ env`, and an empty recipe level would silently drop what the
recipe declared. Nothing the group sees changes — `GroupHandler` already builds
its policy from the same settings through the same `GroupPolicy`, so the
materialized setpoints it now receives produce the identical policy.

**An env level with no single group fails the boot.** The design names only the
named-profile case. Letting env setpoints land nowhere would be the silent
fallback section 10 rules out, so the refusal is the same one.

**The boot failure and the core's lifespan.** Design section 10 says the boot
failure makes "the lifespan fail and the server not start". It cannot:
`Lifespan._run_hook` catches what a hook raises, logs it and continues — its own
docstring says so — and `Lifespan.__call__` then sends
`lifespan.startup.complete`. The exception DOES leave `on_startup` and the module
logger DOES carry the violations, which is what T4 and T22a ask for; the server
is up afterwards with no pool, so every request to that front breaks instead of
being refused politely. The phase closed `[!]` with the plan-defect claim rather
than editing the contract or reaching into lifespan.py, which would change the
boot of every application in the core.

## Phase 6
- Plan-defect claim CONFIRMED by the foreman against src/genro_asgi/lifespan.py:118
  (`_run_hook` catches every hook exception and carries on — documented contract), and
  the remedy ratified by the owner (2026-08-28): design section 10 stands — a broken
  named profile must stop the server. The core grows ONE explicit road:
  `FatalBootError` (name ratified by the owner) in src/genro_asgi/lifespan.py — an
  exception an `on_startup` hook raises to declare its failure fatal to the server.
  `_run_hook` does not swallow it on startup; `Lifespan.__call__` answers
  `lifespan.startup.failed` (message = the exception text) instead of
  `startup.complete`, so uvicorn exits. Ordinary exceptions keep today's
  logged-and-continue isolation; the shutdown sequence is untouched.
- Repair mandate: implement FatalBootError as above (+ its test in
  tests/test_lifespan.py), make the spa app's boot failure raise it (wrapping the
  violations message), re-run T3 as written — the contract test is NOT edited.
  Phase 6's Files grow src/genro_asgi/lifespan.py and tests/test_lifespan.py by this
  decision.

## Phase 8
- The README stays at Version 0.1 / 🔴 DA REVISIONARE: only the owner lifts a document's
  review status, so a docs phase never promotes it.
- The "Applying a profile" section was placed before "Security posture", so the security
  paragraph stays the last word of the archive document.
- CLAUDE.md gained one paragraph before "Not yet built (second pass)" and nothing was
  removed from that list: this plan built no item of it.

## Phase 9
- `ruff format` was not run on the file set. It would reformat 10 of the 19 files, but
  also 97 of the repository's 210 Python files: the tree is not ruff-format-clean, so
  the tool is not this project's formatter and applying it to this plan's files alone
  would leave them formatted differently from everything around them. The blocking
  linter the project actually configures (`ruff check`, rule set `E4,E7,E9,F`) was the
  signal used, and it was already clean.
- The convergence loop stopped after one cycle by its own early-stop rule (no progress
  possible: cycle 1 found nothing). Cycles 2 and 3 were not spent.
- No source or test file was modified by this phase. `review.md` is the whole output,
  which is why `Files:` lists it alone.
- `tests/orchestration/test_orchestration_foundations_e2e.py` differs from the branch
  base but belongs to no phase's `Files:`; it was changed by the out-of-workflow commit
  ec108ed that unblocked phase 2. It was left alone rather than absorbed into this
  phase's scope.

## Run inspection
- Four launcher runs, 9/9 phases closed. Two stops were the launcher's own gates and one
  was the foreman's answer to a consult; none was a defect in the landed work.
- Pre-flight refused the FIRST launch: Phases 2 and 8 were written at Effort=low, and light
  mode ships no contract doctrine. Raised both to medium (commit 2e27955) — a plan carrying
  contract tests cannot have low-effort phases, worth knowing at authoring time.
- Phase 2 came back `[~]` blocked on a red baseline nobody owned: under the run's own load the
  full suite failed one load-sensitive orchestration timing test per run, a different one each
  time. Diagnosed as the TESTS assuming presentation times a loaded machine does not honour;
  fixed outside the workflow by ec108ed (process_ping_timeout opens wide at birth, each
  scenario sets the window it actually measures), then the phase ran clean.
- Phase 6 raised a plan-defect claim on T3 and the run held for the consult. The claim was
  TRUE about the core (`Lifespan._run_hook` swallows every hook exception) and the owner
  ratified the road that keeps the contract: FatalBootError. Recorded in `## Phase 6` above.
- The phase-6 repair session hit the ACCOUNT SESSION LIMIT after 19m36s (fable), and the opus
  retry died in 4s on the same limit — the launcher read exit 1 as "did not run" and stopped
  the run. But the session had already done the whole mandate and left it uncommitted: the
  foreman verified the in-flight tree (T3 green as written, contract copies byte-identical,
  full suite 1627, ruff clean) and committed it as af83cd4. A repair killed by a quota leaves
  work worth checking before relaunching one.
- Phase 3 took two decisions with nobody to ask: the name GroupPolicyError, and from_settings
  as a @classmethod against the "instance methods only" rule (the ratified call site is cited
  verbatim by the design and by three later phases). Both are in review.md for the owner.
- Phase 7 landed no code and could not: in builders the attributes of a subbuilder envelope
  belong to the host grammar, and the site dialect's `application` element is already open, so
  the ratified placement was already reachable. What it added is the declaration a recipe
  author reads.
- Phase 9 found nothing mechanical to fix (ruff clean at cycle 1) and flagged 4 findings plus
  the phases' own 4 `> Review:` notes. `ruff format` deliberately not run: it is not this
  project's formatter (it would reformat 97 of 210 files).
- 36 `wf:phase-N:new` markers stand in src/ for the whole-workflow naming review.

## Naming review (quality check, 2026-08-28)

Owner's rule, given at the review: `profile` alone is too vague — use it only
where the orchestration context is already established, otherwise
`orchestration_profile`.

Applied to the neutral module, which sits in the package root with no import
from `applications/` or `spa/`, so nothing around it says orchestration:

- `src/genro_asgi/profile_store.py` → `orchestration_profile_store.py`
  (and `tests/test_profile_store.py` → `tests/test_orchestration_profile_store.py`)
- `ProfileStore` → `OrchestrationProfileStore`
- `ProfileNameError` / `ProfileNotFoundError` / `ProfileContentError` →
  `OrchestrationProfileNameError` / `OrchestrationProfileNotFoundError` /
  `OrchestrationProfileContentError`
- `PROFILE_NAME` → `ORCHESTRATION_PROFILE_NAME`;
  `MAX_PROFILE_BYTES` → `MAX_ORCHESTRATION_PROFILE_BYTES`

Left short by the same rule, because the containing name already establishes
the context: the store's own methods (`get_profile_name`, `get_profile_path`,
`read`, `write`, `delete`), everything under `spa/orchestration/`
(`active_profile`, `profile_version`, the `profile` / `profile_name` arguments
of `apply_group_settings`), and `SpaCommander.profile_store`.

`tests/test_configuration_profiles_application.py` needed no edit: its only
occurrences are `app.profile_store`, the attribute, which stays. The first
`Must not break:` line holds — the file is still byte-identical to the plan
commit.

### Owed: `orchestration` as a child element of the application

The two kwargs `profiles_path` and `profile_name` on `SpaApplication` are the
vague case the rule targets — a recipe author writes them flat among the other
application kwargs. They were NOT renamed, and should not be: the owner's
answer is to nest them instead.

Phase 7 established the rule that makes this the only declarable placement: in
builders the attributes of the envelope `applications.<code>` belong to the
site dialect, its CHILDREN to the mounted grammar (`config/elements.py:310`).
So `SpaApplicationGrammar` can declare an `orchestration` element, sibling of
`commander`, carrying `profiles_path`, `profile_name` and `control` — closed
and validated, where the three flat words could only be documented in a
docstring.

What it costs, so the plan that does it starts from measured ground:

- the handler reader is the twin of `commander_kwargs` (`config/handler.py:303`):
  `closed_attrs("applications.<code>.orchestration", ...)`;
- `env_settings` stays out — it is a runtime dict, no grammar word;
- the obstacle is `orchestration_control`. Today the gate acts in
  `__init__` (`spa_app.py:391`): `add_branches` mounts `OrchestrationControl`
  under `_orchestration` while the app is built. A child element is readable
  only in `on_startup` — "an application reaches its own subtree only once a
  server has it". So either the route mount moves to `on_startup` (whether the
  router accepts branches on an already-mounted app was NOT verified), or the
  gate stays a constructor kwarg and the element carries only the other two,
  which is a hybrid worse than either shape;
- the third `Must not break:` line has to be renegotiated with the bridge
  (genropy-asgi, `wf/macro2-replica-convergence`), which consumes the flat
  kwargs, and Phase 7 has to be rewritten.
