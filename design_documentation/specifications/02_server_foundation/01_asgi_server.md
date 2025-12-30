# AsgiServer: The Orchestrator

The `AsgiServer` is the application entry point and coordinates all shared resources.

## Responsibilities
- Loading configuration.
- Managing the Middleware pipeline.
- Orchestrating the lifecycle via Lifespan.
- Hosting and mounting `AsgiApplication` instances.

## Internal Architecture
The server maintains a registry of mounted applications and delegates routing to the `Dispatcher`.
