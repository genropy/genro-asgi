# Claude Code Instructions - genro-asgi

**Parent Document**: This project follows all policies from the central [meta-genro-modules CLAUDE.md](https://github.com/softwellsrl/meta-genro-modules/blob/main/CLAUDE.md)

Read the parent document first for:
- Language policy (English only)
- Git commit authorship rules (no Claude co-author)
- Development status lifecycle (Pre-Alpha → Alpha → Beta)
- Standardization requirements
- All general project policies

## Project-Specific Context

### Current Status
- **Development Status**: Beta
- **Has Implementation Code**: Yes
- **GitHub**: https://github.com/genropy/genro-asgi

### Project Purpose

Minimal ASGI server core, spec-first redesign of `genro-asgi` — see `SPECIFICATION.md`.

### Project-Specific Guidelines

- This repository starts from a ratified design specification rather than
  ported code. `SPECIFICATION.md` is the founding decision log and the
  source of truth for the redesign until implementation begins.

### Known Issues

- None yet.

### Related Documentation

- `SPECIFICATION.md` — founding specification and decision log.

## How it works — the whole machine at a glance

*(Update this section in the SAME commit that changes the behaviour it
describes: a stale overview misleads more than no overview.)*

### The server layer

`BaseServer` is composed with its **applications** (fixed at construction,
keyed by `code`, mounted by first path segment — D29 demux: segment match →
that app with the segment stripped; else the root app; else 307 to the
declared default; else the site index on `/` (ratified 2026-08-24, not yet
built — today 404); else 404). It owns one thread pool (`run_sync`), a
`RequestRegistry` holding the in-flight picture, ordered lifespan, and boots
uvicorn programmatically (`serve()`, CLI `genroasgi serve/apps/stop/remove`,
`--debug` = a declared usage mode the core never branches on). The server
carries a lifecycle `state` (`lifespan.py`: `RUNNING`/`QUITTING`/`STOPPING`):
anything but RUNNING answers 503 + `Retry-After` and registers nothing, while
what the middleware chain serves itself passes. `Lifespan.shutdown` turns the
state first (to `shutdown_mode` — STOPPING by default, QUITTING set by the
reload child in `factory()`), drains the in-flight requests (bounded), THEN
runs the hooks in reverse.
Middleware wraps the dispatch (errors, authentication, session, cors,
logging, wellknown). Auth answers **401 to the anonymous, 403 to the known**;
admin surfaces live under the `_server` app as sections (auth, monitor,
users, tokens, tasks) gated by `SERVER_ADMIN`; the monitor renders one page
over every mounted app via the `app_snapshot`/`app_panel`/`panel_source`
contract on `BaseApplication`. Sessions: `MemoryStore`, cookie
`Max-Age = ttl x 24`. Filesystem access goes **only through storage nodes**
(logical volumes, e.g. `GENROASGI:frozen_users`); storage is pinned
synchronous (`StorageMixin` calls `set_sync()`, tests pin the same) — never
`await` a storage node call here. Config comes from the config builder + CLI;
`OpenApiApplication`, `McpApplication` and the tasks subsystem (scheduler,
spool, executor) mount like any other app.

### The SPA machine (`spa/` + `applications/spa_app.py`)

**One stack.** The repository cutover happened on 2026-08-22: `main` and the
tag `v0.35.0` freeze the last dual-stack state (the pre_refactoring
`UserStickyCommander`/`UserStickyWorker` and their front), and `develop` —
the base of all work branches — carries ONLY the new core:
`spa/orchestration/` fronted by `applications/spa_app.py` (`SpaApplication`,
which took the vacated name; it was `SpaApplicationNew`). "pre_refactoring"
now names code that lives only on `main`/`v0.35.0`. Say never "legacy": in
this code that word names the genropy SITE (`WsgiSeam`, "legacy WSGI
sites"). genropy-asgi will be rebased on develop; NO PyPI release from
develop until that bridge is migrated — the published bridge pins the
frozen tag.

**Ownership chain.** server → `SpaApplication` (stateless front: cookie,
two-stage demux, HTTP translation — 503 with `Retry-After` for a refusal,
502 for a site failure) → `SpaCommander` (global indexes, lifecycle,
barrier, request chain, single-writer fold via `EnvelopeHandler`, freezer
via `FreezeHandler`, `DeliveryDesk`) → n `GroupHandler` (placement,
capacity, growth and shrink) → n `WorkerHandler` (process, wire,
surveillance) → `SpaWorker` (the live users/connections/pages state and the
hosted WSGI site behind `WsgiSeam`). Usersticky principle unchanged: ALL
pages of a user live in the same process as the user's store. A group whose
recipe declares `engine_factory` owns a **template process**
(`template_entry.py`, synchronous, one per group): it builds the group
engine once, freezes its heap, and every worker of that group is a `fork`
of it (`template_connector.py`, `worker_process.py`; `WorkerEntry` hands
the inherited `group_engine` to the worker). Without the factory the group
spawns workers the ordinary way and has no template.

**Identity — one, the site's own.** The `spa_connection_id` cookie carries
the hosted site's OWN connection id (owner decision 2026-08-22): the front
mints nothing, the site names the connection while serving, the answer
carries that id back and the cookie is written with it (rewritten only when
it differs from the one that came in). `connection_user_map` and
`page_connection_map` are keyed by real connection ids and the deposit
files one parcel per connection under that same id. The cookie lives 24
hours, the life the site gives its own connection.

**Data plane (landed 2026-08-20, 14 phases).** Datachanges and dbevents are
delivered ADDRESSED through the `DeliveryDesk` (subscriptions, pending
mailboxes, age-bounded events); the global store lives ONLY on the
commander — no replicas — with reads as calls on the lane (`store_get`) and
read-modify-write through the lock grant/release, the grant carrying the
true master state; never files or shared memory between processes.

**Mobility and deaths.** One path only: hold → freeze → reassign →
unfreeze, used for compaction, ordered replacement and wake — the direct
worker-to-worker move of the pre_refactoring stack was deliberately
eliminated, not left behind. A request meeting a user between two homes
parks on the per-user barrier up to `REQUEST_HOLD_MAX_SECONDS`. A sudden
worker death restarts the small set of users involved: an accepted,
observable risk, not a gap.

**Putting ONE user to sleep is one ordered operation, and the group owns it**
(wf/41, landing): `GroupHandler.freeze_hosted_user` blocks him at the vertex
(`hold_user`), orders his worker (`/op/freeze_user` →
`SpaWorker.freeze_designated_user`), and the REPLY IS the confirmation — the
`user_frozen` event rides it, so the fold has already marked, released and
unplaced him when the caller is answered; a refusal releases the hold
(`SpaCommander.release_user_hold`) and leaves him where he was. WHO sleeps is
the group's judgment too: `GroupHandler.check_user_activity` is its second
periodic and reads the two REAL clocks off each worker's last photo — silence
past `user_idle_freeze_minutes` (now a GROUP setting, no longer the worker's)
is parked, silence past `SpaCommander.get_user_expiry_seconds` is dropped
(`/op/drop_user`). The worker keeps no gauge and takes no departure decision
of its own.

**The reboot (landed 2026-08-25, wf/33).** A server that leaves QUITTING
takes the soft quit: `SpaCommander.quit` stops the clock, orders every group
(`GroupHandler.quit_all`) to park its users in `reboot_temp` — each group
BLOCKS at the vertex every user it places on a worker BEFORE ordering that
worker away, so no request of his walks into a process already emptying, and
each hold falls as its freeze confirms; each worker swaps its `FreezeHandler`
onto that root, freezes each user as his last call
ends, and CUTS the stuck ones past `PENDING_CALL_GRACE_SECONDS` (the user is
parked anyway; the lost answer reads 503 via the front, which tells a wire
lost while quitting from a real 502) — then writes its own
`commander_register_item.pickle` (the three maps normalised + the global
store: the indexes are SAVED, not rederived — D-h supersedes F4 here, the
cookie's cid→user lives only in `connection_user_map`) and commits by
renaming to `reboot_data` (F5: the final name IS the completeness proof).
On boot `SpaCommander.start` runs `adopt_frozen_registers`: wipe the working
deposit ALWAYS (F4), drop a leftover `reboot_temp` unread, read the commander
item BEFORE moving anything (unreadable → clean boot, said once), rename
`reboot_data` onto the working deposit, load the maps (everybody frozen,
nobody pre-warmed — the lazy wake is the only road back), then
`drop_expired_users(now=True)`. Under `serve --reload` every exit saves
(dev-reload auto-soft): verified live — same cookie, new process, same
identity, no re-login. Decision record:
`temp/decisioni_registri_cancello_2026-08-25.md`.

**The orchestration profile applied (landed 2026-08-28).** A stored profile
reaches the live pool. The whole pool hangs under ONE node of the front —
`application → orchestration → commander → groups → group`: `SpaApplication`
reads `profiles_path`, `profile_name` and `control_enabled` off
`applications.<code>.orchestration` at boot (never constructor kwargs — a recipe
still writing them, or `orchestration_control`, on the application element is
refused by name), plus `env_settings` (a runtime dict on the application element,
no grammar word). The node is REQUIRED and so is the commander under it: a spa
front declared without either does not boot (`FatalBootError` →
`lifespan.startup.failed`) — wanting no pool means declaring no spa front. At
boot `boot_group_settings` composes `defaults ⊕ recipe_settings ⊕ profile ⊕ env_settings` through
`GroupPolicy.from_settings` — the frozen dataclass in
`spa/orchestration/group_policy.py` that holds the 16 setpoints, IS the
validation and collects every violation — BEFORE the vertex is built; the recipe
and env levels stay separate dicts, so every later apply recomposes from them.
A missing or invalid profile raises `FatalBootError` (`lifespan.py`): the one
exception `_run_hook` lets through on startup, which answers
`lifespan.startup.failed` and exits the server. No silent fallback. Hot apply is
`SpaCommander.apply_group_settings` under `_configuration_lock` for the whole
apply: stage 1 fallible and mutation-free (read, compose, diff, sha256 digest,
CPU reconciliation list, payload), stage 2 a plain `def` of guaranteed
assignments — `GroupHandler.apply_policy`, `active_profile`,
`configuration_generation` (+1 even when idempotent), `last_apply` — stage 3 best
effort (the `apply_group_settings` and `cpu_policy_reconciled` audit lines,
`ping_now()`). Storage is shared with the `_sysop` archive through `OrchestrationProfileStore`
(`orchestration_profile_store.py`). Routes, mounted under `_orchestration` only
when the gate is on — and mounted LAST, after the vertex is built and started, so
a failed boot leaves the router untouched; that the root is FREE is established
before anything is built (a root the front's own router already claims is a fatal
boot with no vertex constructed), and an unexpected mount failure takes the pool
back down. The lifecycle is closed: a startup on a live pool does nothing, a
shutdown lets the vertex go in `finally`, and the startup after it builds a new
one without remounting the route. Routes: `POST apply`
(the body is the profile level, active profile becomes null), `POST reload`
(`{"name": ...}` or the active one), `GET status` (read-only, no lock). Exactly ONE group per named profile — a boot failure or a
409 (`SingleGroupRequired`) otherwise. Details:
`internals/10_server/020_applications/configuration_profiles/README.md`.

**The retirement holds through CPU pressure (landed 2026-08-28).**
`cpu_retirement_quiet_seconds` (group setpoint, default 60.0, `>= 0`) is how
long the CPU must stay silent before `check_occupancy` may close a worker again.
`GroupHandler.record_cpu_pressure` stamps the clock on every CPU event — a
worker blocked or reopened — and on an `apply_policy` that actually MOVES a
worker's admission;
an apply that moves nobody invents no cooldown. `get_retirement_suspension`
answers the gate: a living worker still CPU-closed, or an event younger than the
quiet. `_cpu_pressure_monotonic` is born `None`, so a boot imposes no cooldown,
and with `cpu_admission_close_percent` off the gate is never consulted. Past the quiet
`_spare_worker` and `_order_quit` are exactly what they always were —
consolidation of a worker with users included.

**The CPU picks the worker; the memory only refuses (landed 2026-09-02).** A
filtered temperature above `cpu_admission_close_percent` closes a worker to new
users; one below `cpu_admission_reopen_percent` reopens it. `assign_user` walks
the CPU-open workers HOTTEST first (the filtered temperature, never memory) and
skips one that admitted somebody less than `worker_admission_interval_seconds`
ago (1.0 s); when every open worker is in its window the hottest that admits
takes the user anyway (`all_workers_recently_admitted`) — the interval orders,
it never refuses and never births. `WorkerHandler.assign_user` judges state,
`worker_max_users` and the memory veto `worker_memory_admission_percent` (80,
`< restart_occupancy_max_percent`); nobody estimates a user's cost any more — the
row at the vertex carries no `occupancy_percent`, the census shows memory and
temperature per worker. When no open worker admits, `assign_user` creates one
worker under the placement lock and assigns that same user before returning;
refused the birth, a CPU-closed worker under the veto takes him as a logged
fallback. The periodic judge births nothing: a group with no living worker gets
its reception back when the memory affords it. Journal: `hottest_cpu_open_candidate`,
`worker_recently_admitted` / `worker_memory_full` on the candidate rows,
`all_workers_recently_admitted`, `new_worker_created_for_placement`,
`cpu_closed_hard_cap_fallback`.

**Worker CPU temperature is a separate measurement channel (landed
2026-09-01; filtered 2026-09-02).** One commander-side task reads each worker's
cumulative process CPU clock through psutil at `cpu_temperature_sample_seconds`
(100 ms by default) and derives the share of one core burned over the real
interval. That raw sample is telemetry only (`cpu_temperature_sample_percent` in
the census): what every CPU judge reads is `cpu_temperature_percent`, the samples
through an asymmetric first-order filter — `1 - exp(-dt/tau)`, `tau` =
`cpu_heating_seconds` (1.0) when the sample is hotter, `cpu_cooling_seconds`
(5.0) when colder, both group setpoints — seeded by the first sample. It sends no
worker RPC and writes no worker photo. The sampling pass reconciles admission;
placement uses that gate, and heartbeat offload uses the same filtered value.
Memory, per-user activity and every non-CPU decision stay on their existing
channels.

**A CPU-hot worker slims one user per beat (landed 2026-09-01).**
`cpu_offload_percent` (group setpoint, off by default; requires
`cpu_admission_close_percent` and sits above it — reopen < close < offload) arms
`GroupHandler.check_cpu_offload`, run at EVERY heartbeat on fresh photos: the
hottest CPU-closed `running` worker past the threshold cedes ONE user through
`freeze_hosted_user`. WHO is judged against the window itself: a MATERIAL
contributor holds at least half the fair share of the interval's service time
(`s >= S/(2N)`, S = summed `recent_service_seconds` of the active users, N
their count) or has a call in flight; negligible activity is never a
candidate. The cession takes the least busy material contributor WITHOUT
calls in flight (least `recent_service_seconds`, then least
`recent_call_count`, then name) — a user mid-call is never transferred, and
material contributors all busy defer the cession to the next beat. The source
is closed, so his next request is placed elsewhere or births capacity
(demand-driven); light contributors leave one per beat and the load's owner
stays — a single material contributor is never transferred, journaled once as
`single_user_overload`. A cession stamps `record_cpu_pressure`; standing
conditions are journaled once per (condition, subject) via a marker on the
handler, never every beat, and every row carries the numbers that rebuild the
judgment (CPU, S, N, threshold, active/material/cedible counts). Reason
codes: `cpu_offload_threshold`, `cpu_offload_user_selected`,
`cpu_offload_completed`, `cpu_offload_refused`,
`cpu_offload_no_active_candidate`, `cpu_offload_deferred_pending_calls`,
`single_user_overload`.

**The photo counts each user's service (landed 2026-09-01).** Every user row
carries three counters written by the worker — ``served_call_count`` and
``service_seconds`` cumulated in the ``finally`` of the actual stitching
(failed and slow calls counted like any other), ``pending_call_count`` read
off the pendings — and two derived by ``WorkerEnvelopeHandler`` between two
photos, ``recent_call_count`` / ``recent_service_seconds``, the same road
``cpu_seconds`` takes to ``cpu_percent``. The worker keeps no window and takes
no decision; the counters live in the register item and never reach a frozen
parcel (the freeze persists store and connections, not the row).

**Every orchestration decision carries its reason (landed 2026-08-29).**
The human `orchestration_log_path` remains unchanged; beside it the commander
writes `<stem>.decisions.jsonl`, independently rotated and never mixed with
stdout. `SpaCommander.log_order` mirrors every issued order into that journal,
while `log_decision` records calculations that deliberately issue no order.
Each JSON row carries schema, process-local sequence, UTC timestamp, decider,
decision, subject, outcome, a stable reason code, numbers and the candidates
the judge saw. Group placement records every CPU-open candidate in
fullest-first order; CPU admission scans record transitions, thresholds, open
and empty worker counts; a demand-driven birth is recorded on the placement
that immediately occupies it; retirement records its suppression or the absence of an
absorbable spare. The journal observes policy — it never changes placement,
growth, retirement or restart behaviour.

**Not yet built (second pass).** The deliberate reboot command on `_server`
(`reboot now`/`reboot wait N`, notify_user, the consumer service-message
lane); the single-group reboot (needs no photo — the commander survives) and
the runtime/bundle path classifier for the reload watcher; pool monitor
parity and Prometheus metrics; the in-process local worker; the parent-side
escalation after a partially applied fold (F48/F49 — cited by code and
commits, still to be entered in the register). Decision registers:
`temp/interview_handler_2026-08-15.md` (F1-F49); design:
`temp/design_orchestrazione_v4_2026-08-17.md`.

---

**All general policies are inherited from the parent document: [meta-genro-modules CLAUDE.md](https://github.com/softwellsrl/meta-genro-modules/blob/main/CLAUDE.md)**

**Last Updated**: 2026-09-02
