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
keyed by `code`, mounted by first path segment — D3 demux: segment match →
that app with the segment stripped; else the root app; else 307 to the
declared default; else 404). It owns one thread pool (`run_sync`), a
`RequestRegistry` holding the in-flight picture, ordered lifespan, and boots
uvicorn programmatically (`serve()`, CLI `genroasgi serve/apps/stop/remove`).
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

**Two stacks, and the words for them (until Macro 6).** Everything in this
section describes the **pre_refactoring** stack — `spa/worker.py`
(`UserStickyWorker`), `spa/commander.py` (`UserStickyCommander`),
`applications/spa_app.py` (`SpaApplication`) — which is what genropy-asgi runs
on today and which the orchestration rebuild has not touched by a single line.
The **new core** is `spa/orchestration/` + `applications/spa_app_new.py`. Say
neither of them "legacy": in this code that word already names the genropy SITE
(`WsgiSeam`, "legacy WSGI sites"). The pre_refactoring stack goes at the Macro 6
cutover, and this note with it.

**Identity.** `SpaApplication` is a thin front: it reads/mints the
`sticky_cid` cookie ONCE per request (the cid), derives the routing identity
from the commander's own surface — `connection_user.get(cid, cid)` — and
keeps ZERO state. **Whoever shows up is a user in full**: received by the
reception worker, named `guest_<cid>` (`GUEST_PREFIX`, the daemon's own
convention), registered through the fold like anybody else. At login the
connection is re-labeled onto the root avatar identity
(`change_connection_user`); nobody can log in AS a guest. A **stranger** is
an identity the pool holds nothing of — no placement, no frozen parcel
(a cookie that outlived a restart without dump, a parcel reaped by age).

**The chain.** cookie → cid → `connection_user` (commander index) →
`user_worker_map` → the worker. Usersticky principle: ALL pages of a user
live in the same process as the user's store. The surface is a tree —
users → connections → pages, with inverse maps — written ONLY by the fold
(single writer); THE MAP IS WRITTEN AT THE DECISION: a user lives where it
logged in, and if `decide_worker` (reception-first) says it belongs
elsewhere, a detached move carries it later.

**Pool anatomy.** One `UserStickyCommander` (in the server process) speaks to
N `UserStickyWorker` children over the channel: a `ChannelHub` (UDS or TCP),
typed frames CALL/REPLY/EVENT, every REPLY carrying three sub-envelopes
(synchronous class settled in the caller's coroutine — logins included;
task class drained detached). A `local_worker` variant runs in-process over
`LocalChannel` — same protocol, no fork. Legacy WSGI sites are served
in-process by the worker through `WsgiSeam` (WSGI as adapter, never as
transport). The global store MASTER lives on the commander; replicas on the
workers, updated by captured changes; read-modify-write goes through the
global lock grant.

**Health vs shape.** Each worker has a `caretaker` probing it every 5s —
health ONLY: a mute worker (or one sitting on an unanswered `add_user`
delivery past `max_pending_cycles`) is killed; `reconcile_loop` keeps
living == target, respawns the shortfall, buries tombstones. The pool's
SHAPE is decided on a slow clock: `planner` every `decision_interval` reads
ONE picture (`pool_occupancy`, judged by the evaluator in saturation space)
and `build_plan` answers with the ordered ladder — **1 FREEZE idle users to
disk, 2 REBALANCE the hot, 3 REPLACE the condemned (memory-floor NECESSITY
first, waste CONVENIENCE after; spawn gated on the pool absorbing the users),
4 SPAWN a spare, 5 COMPACT the slack** — claiming every named worker
(`retiring`) in the same synchronous breath. `execute_plan` runs steps one
at a time, re-asking each; a failed spawn leaves the pool `restricted`:
everybody inside is served as ever, strangers get 503 + `Retry-After` until
a fresh REGISTER proves the pool can grow again.

**Moves and the freezer.** A move is FLAG → QUIESCE → evict → install →
SWITCH, under a per-user barrier every forward parks on; past the evict the
parcel exists only in the commander's custody, salvaged onto another worker
if the destination dies. The freezer parks idle users on disk (one parcel
per user under `frozen_users_dir`, identity flattened by `user_to_userkey`,
one-way); the wake is LAZY — `resolve_worker` finds the `FROZEN` placement
and re-installs the parcel on the user's own next request; orphan parcels
die by age (the reaper). `hard_restart` is the declared exception to
"successor first": park everybody in the freezer, kill, respawn under the
same name, refill lazily. `dump`/`restore` carry the whole surface across a
full server restart.

**Where the rebuild stands.** The split the pre_refactoring commander needed —
`SpaCommander → n GroupHandler → n WorkerHandler` — is BUILT and on main, under
`spa/orchestration/` (Macro 1-4: foundations, worker process, commander and
groups, request chain and login), fronted by `SpaApplicationNew`. It knows who
lives where, how a request reaches its worker, the freezer, the deaths, the
groups and the occupancy — and nothing of the data plane: no datachanges, no
table events, no store writes from the hosted site, no hot move, no
`dump`/`restore`. That is why genropy-asgi cannot run on it yet. Macro 5 builds
the data plane — the minimum measured in
`temp/minimo_genropy_pre_alpha_2026-08-19.md` — and Macro 6 is the cutover, when
the pre_refactoring stack is removed. Decision register:
`temp/interview_handler_2026-08-15.md` (F1-F49); design:
`temp/design_orchestrazione_v4_2026-08-17.md`.

---

**All general policies are inherited from the parent document: [meta-genro-modules CLAUDE.md](https://github.com/softwellsrl/meta-genro-modules/blob/main/CLAUDE.md)**

**Last Updated**: 2026-08-19
