# Stateful Worker Management

Managing long-running SPAs requires a shift from stateless calls to state-aware workers.

## Resident State
Unlike standard REST APIs, complex SPAs often maintain a "dirty" state in memory (e.g., active database transactions, transient UI data). Genro-ASGI manages this through workers that "host" specific sessions.

## Session Affinity
The routing layer identifies the session ID and ensures the request reaches the worker where the session was initialized. This avoids the cost of serializing and de-serializing the entire application state for every HTTP call.

## Page Lifecycle Tracking
The `SpaManager` tracks:
- **Active Connections**: Which pages are currently connected via WebSockets.
- **State Expiry**: Automating the cleanup of workers when sessions are inactive for a defined period.
