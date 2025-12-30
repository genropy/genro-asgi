# Future Developments and Scalability

The roadmap for Genro-ASGI includes features to support global-scale and high-resilience applications.

## NATS Integration
Replacing local IPC with NATS to allow workers to scale across multiple machines while maintaining session routing logic.

## State Migration and Blue-Green Deployment
- **Live Migration**: The ability to move a session state from one worker to another without disconnecting the client.
- **Zero-downtime Updates**: Routing new sessions to updated workers while allowing old sessions to complete their lifecycle on the previous version.

## Advanced Inter-Process RPC
Expanding the WSX protocol to work seamlessly across the NATS bus, making the physical location of the worker transparent to the developer.
