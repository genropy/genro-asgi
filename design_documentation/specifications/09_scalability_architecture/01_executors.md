# Executor System

Genro-ASGI handles concurrency by managing how tasks are executed across different resources.

## Async Event Loop
The primary loop handles all I/O bound operations (network, some storage tasks) using Python's `asyncio`.

## Thread and Process Pools
For CPU-bound tasks or blocking legacy code, Genro-ASGI uses an **Executor Registry**:
- **Default Executor**: A thread pool for standard blocking calls.
- **Custom Executors**: Can be defined in the configuration (e.g., a specific process pool for image processing).

## Usage
Handler methods can specify which executor to use for specific operations, ensuring that the main event loop is never blocked by heavy computations.
