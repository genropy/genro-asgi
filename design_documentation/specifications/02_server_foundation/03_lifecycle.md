# Server Lifecycle and Lifespan

The ASGI Lifespan protocol allows Genro-ASGI to manage startup and shutdown sequences reliably.

## Startup Sequence
1.  **Server Initialization**: Configuration is loaded and the orchestrator is created.
2.  **Middleware Setup**: The middleware chain is initialized.
3.  **App Discovery**: Applications are instantiated (`on_init`).
4.  **Lifespan Startup**: The server sends the `startup` signal.
5.  **App Startup**: Every application's `on_startup` hook is executed.

## Shutdown Sequence
1.  **Lifespan Shutdown**: The server receives the termination signal.
2.  **App Shutdown**: Every application's `on_shutdown` hook is executed (e.g., closing DB pools).
3.  **Final Cleanup**: The ASGI server completes the process.
