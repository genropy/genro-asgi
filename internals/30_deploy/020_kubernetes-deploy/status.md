# Kubernetes deploy — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## Proposal boundary

The commander-controlled Pod runtime is an unratified proposal. Source contains
local spawn/template/fork worker processes and filesystem freezer parcels; it
does not contain the proposed Kubernetes worker lifecycle, shared cross-node
freezer or generation-fencing controller.

The existing worker process abstraction and resource accounting are prerequisites,
not proof that phases K0–K6 have landed. In particular the failed-fold coherence
question must not disappear merely because a worker wire reconnects. No
Kubernetes deployment recipe is presented as executable.

Behavior evidence: [`WorkerProcess`](../../../src/genro_asgi_multiworker_spa/orchestration/worker_process.py#L48), [`FreezeHandler`](../../../src/genro_asgi_multiworker_spa/orchestration/freeze_handler.py#L88).

## Source and test evidence

- [src/genro_asgi_multiworker_spa/orchestration/spa_commander.py](../../../src/genro_asgi_multiworker_spa/orchestration/spa_commander.py)
- [src/genro_asgi_multiworker_spa/orchestration/group_handler.py](../../../src/genro_asgi_multiworker_spa/orchestration/group_handler.py)
- [src/genro_asgi_multiworker_spa/orchestration/worker_process.py](../../../src/genro_asgi_multiworker_spa/orchestration/worker_process.py)
- [src/genro_asgi_multiworker_spa/orchestration/freeze_handler.py](../../../src/genro_asgi_multiworker_spa/orchestration/freeze_handler.py)
- [tests/spa/orchestration/test_orchestration_group_handler.py](../../../tests/spa/orchestration/test_orchestration_group_handler.py)
- [tests/spa/orchestration/test_orchestration_worker_process.py](../../../tests/spa/orchestration/test_orchestration_worker_process.py)
