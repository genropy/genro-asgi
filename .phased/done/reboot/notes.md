# Notes — wf/33-reboot

## Phase 1 — the shutdown window under `--reload`, measured

Measured on 2026-08-25 on this branch, macOS, uvicorn's `StatReload`. The probe
was a one-file `RoutedApplication` under `temp/probe/` whose `on_shutdown`
logged a timestamped line every second for 60 seconds; a reload was triggered
by touching a second file in the watched directory. Commands and raw log kept
out of the tree (`temp/` is gitignored).

**The reloader is a parent process holding one child.** Parent pid 27242,
child 27244. The child is the one that serves. The CLI's pidfile records the
PARENT, which is what `stop` must signal (`__main__.py:388-390`, already
documented there).

**The signal.** In the child, `SIGTERM` and `SIGINT` are both bound to
`uvicorn.server.Server.handle_exit`; `SIGHUP` is `SIG_IGN`. So the child is
asked to leave through uvicorn's own exit path, not through a handler of ours.

**The lifespan shutdown runs, and NOTHING bounds it.** The sequence on the
console was: `StatReload detected changes in ...` -> `Shutting down` ->
`Waiting for application shutdown.` -> (60 seconds of the hook) ->
`Application shutdown complete.` -> `Finished server process [27244]` ->
`Started server process [29172]`.

Numbers: the hook ran **60.09 s** end to end, uninterrupted — no harder kill,
no truncation. The new child's `on_startup` fired **0.28 s** after the old
child's hook returned.

**Two consequences for this workflow:**

1. The soft quit has all the time it needs. `timeout_graceful_shutdown` is not
   set, so uvicorn waits indefinitely for the lifespan shutdown to return.
   Phase 6 needs no special shape: running the liturgy inside
   `SpaApplication.on_shutdown` is enough.
2. **The two processes never overlap.** The new child starts only after the old
   one has finished, so `reboot_data` written by the dying child is guaranteed
   visible to the one that boots. The soft start cannot run before the soft
   quit completed — a whole class of race does not exist here.

**Confirmed on the side** (already stated in the plan, D-l): the reloader
watches the directory of the source file given to the CLI — the console
printed `Will watch for changes in these directories: ['.../temp/probe']` —
not `src/` of genro-asgi.

**Caveat, declared.** The budget the liturgy chooses is therefore ours alone:
uvicorn will not cut it short, so a quit that hangs hangs the developer's
reload forever. The cut of D-e is what keeps that from happening, and it is
not optional.

## Environment note

`genro-asgi` is installed editable pointing at the PRIMARY worktree, so a
`python`/`pytest` launched inside this worktree would import develop's code.
This worktree has its own `.venv` (`pip install -e ".[dev]"`) which resolves
`genro_asgi` to `worktrees/reboot/src/`. Every command of this workflow runs
through `.venv/bin/`.
