# Soft and hard restart — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## State, drain and uvicorn shutdown

The server distinguishes `RUNNING`, `QUITTING` and `STOPPING`. HTTP dispatch
refuses new work outside RUNNING; WebSocket handshake refusal applies before
accept to both WSX and raw applications. `Lifespan.shutdown` selects the
shutdown mode, drains registered requests with a 10-second bound, then invokes
application hooks in reverse order.

`shutdown_timeout_seconds` (default 5.0) is passed to uvicorn's graceful
connection shutdown. It prevents an endless connection from indefinitely
postponing lifespan; it does not bound every application hook or pool thread.

Claim anchors: [`Lifespan`](../../../src/genro_asgi/lifespan.py#L89), [`shutdown_timeout_seconds`](../../../src/genro_asgi/server.py#L402).

## SPA save and lazy restoration

`SpaApplication.on_shutdown` calls the commander's `quit` path for QUITTING and
`stop` for a dry shutdown. `SpaCommander.quit` gathers users into reboot state
and persists its routing registers. `adopt_frozen_registers` restores frozen
placement information; users wake lazily through the usual request path.
The global store is not part of that restored state.

`reloading.factory` selects QUITTING for a reload child. Session snapshots are
separate and can preserve complete live sessions for a named instance.

Claim anchors: [`SpaApplication`](../../../src/genro_asgi_multiworker_spa/spa_app.py#L517), [`on_shutdown`](../../../src/genro_asgi_multiworker_spa/spa_app.py#L1002), [`quit`](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py#L1710), [`SpaCommander`](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py#L494), [`adopt_frozen_registers`](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py#L1642).

## Remaining restart target

The general owner-directed hard/soft restart ceremony, user notices,
administrative command and `execv` sequence are not delivered as a single
server command. The earlier blanket claim that none of restart exists is
obsolete: the state/drain, reload survival and SPA persistence pieces above
are implemented. Kubernetes and subcommander reconstruction remain proposals.

Target evidence: [recorded target](design.md); this paragraph records unresolved
design distance, not an executable contract.


## Source and test evidence

- [src/genro_asgi/server.py](../../../src/genro_asgi/server.py)
- [src/genro_asgi/lifespan.py](../../../src/genro_asgi/lifespan.py)
- [src/genro_asgi/reloading.py](../../../src/genro_asgi/reloading.py)
- [src/genro_asgi/session/mixin.py](../../../src/genro_asgi/session/mixin.py)
- [src/genro_asgi_multiworker_spa/spa_app.py](../../../src/genro_asgi_multiworker_spa/spa_app.py)
- [src/genro_asgi_multiworker_spa/orchestration/spa_commander.py](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py)
- [tests/core/test_reloading.py](../../../tests/core/test_reloading.py)
- [tests/core/test_lifespan.py](../../../tests/core/test_lifespan.py)
- [tests/spa/orchestration/test_orchestration_foundations_e2e.py](../../../tests/spa/orchestration/test_orchestration_foundations_e2e.py)
- [tests/spa/orchestration/test_orchestration_spa_commander.py](../../../tests/spa/orchestration/test_orchestration_spa_commander.py)
