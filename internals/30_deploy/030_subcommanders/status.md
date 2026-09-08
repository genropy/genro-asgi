# Subcommanders — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## Proposal boundary

The hierarchy root → subcommander → group → worker is an unratified proposal.
The current ownership chain has one `SpaCommander` directly holding
`GroupHandler` objects and their local workers; there is no subcommander class,
recursive directory, distributed budget lease or epoch/fencing protocol.

A group's policy delegation inside one commander is not delegated distributed
authority. The proposal's choice of root data path, directory persistence,
failure model and meaning of a subcommander remains open. No configuration API
for the proposed hierarchy is claimed to run.

Claim anchors: [`SpaCommander`](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py#L494), [`GroupHandler`](../../../src/genro_asgi_multiworker_spa/orchestration/group_handler.py#L320).

## Source and test evidence

- [src/genro_asgi_multiworker_spa/orchestration/spa_commander.py](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py)
- [src/genro_asgi_multiworker_spa/orchestration/group_handler.py](../../../src/genro_asgi_multiworker_spa/orchestration/group_handler.py)
- [src/genro_asgi_multiworker_spa/orchestration/worker_process.py](../../../src/genro_asgi_multiworker_spa/orchestration/worker_process.py)
- [src/genro_asgi_multiworker_spa/orchestration/freeze_handler.py](../../../src/genro_asgi_multiworker_spa/orchestration/freeze_handler.py)
- [tests/spa/orchestration/test_orchestration_group_handler.py](../../../tests/spa/orchestration/test_orchestration_group_handler.py)
- [tests/spa/orchestration/test_orchestration_worker_process.py](../../../tests/spa/orchestration/test_orchestration_worker_process.py)
