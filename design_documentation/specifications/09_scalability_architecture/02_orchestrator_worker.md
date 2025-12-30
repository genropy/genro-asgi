# Orchestrator and Worker Separation

For high-availability and large-scale deployments, Genro-ASGI supports a separation between the entry-point and the actual processing logic.

## The Orchestrator (AsgiServer)
The orchestrator acts as a lightweight proxy and coordinator. It handles:
- SSL termination (if not handled by an external proxy).
- Initial request dispatching.
- Health monitoring of workers.

## Stateful Workers
Processing logic can be offloaded to worker processes. In stateful scenarios, the orchestrator ensures **Session Affinity**, routing requests from the same session to the same worker where the state is resident.

## Communication
Inter-process communication can be achieved through:
- **Shared Memory/Local IPC**: For single-node deployments.
- **NATS/Message Queue**: For multi-node distributed architectures.
