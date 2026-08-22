# Server

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The ground.** The machine everything stands on, and the applications it hosts.

`BaseServer` composed with its applications — fixed at construction, keyed
by `code`, mounted by first path segment (D3 demux: segment match → that app
with the segment stripped; else the root app; else 307 to the declared
default; else 404). It owns one thread pool (`run_sync`), the
`RequestRegistry` holding the in-flight picture, the ordered lifespan, and
boots uvicorn programmatically. `AsgiServer` composes the mixins on top:
authentication, sessions, middleware, storage, tasks, communication.

Interactions: everything — this is where the other entries are mounted and given their turn.
