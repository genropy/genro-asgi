# Dynamic groups and application bundles — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## Proposal boundary

The bundle/channel/cohort deployment model is an unratified proposal. The
current `GroupHandler` manages local worker capacity and existing group policy;
it is not an S3 bundle builder, promoter or runtime group topology manager.
`SpaCommander.apply_group_settings` applies setpoints to an existing group,
which does not implement bundle promotion or add/remove deployment groups.

No runnable recipe for this proposal is claimed. Decisions D1–D7 of the
historical distribution proposal remain the design input, not an authorization
to implement it.

Claim anchors: [`GroupHandler`](../../../src/genro_asgi_multiworker_spa/orchestration/group_handler.py#L320), [`SpaCommander`](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py#L494), [`apply_group_settings`](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py#L1448).

## Source and test evidence

- [src/genro_asgi_multiworker_spa/orchestration/spa_commander.py](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py)
- [src/genro_asgi_multiworker_spa/orchestration/group_handler.py](../../../src/genro_asgi_multiworker_spa/orchestration/group_handler.py)
- [src/genro_asgi_multiworker_spa/orchestration/worker_process.py](../../../src/genro_asgi_multiworker_spa/orchestration/worker_process.py)
- [src/genro_asgi_multiworker_spa/orchestration/freeze_handler.py](../../../src/genro_asgi_multiworker_spa/orchestration/freeze_handler.py)
- [tests/spa/orchestration/test_orchestration_group_handler.py](../../../tests/spa/orchestration/test_orchestration_group_handler.py)
- [tests/spa/orchestration/test_orchestration_worker_process.py](../../../tests/spa/orchestration/test_orchestration_worker_process.py)
