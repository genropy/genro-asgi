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

**Last Updated**: 2026-08-25
