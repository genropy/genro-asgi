# Global store

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 DA REVISIONARE

One state shared across every user and page, with a safe read-modify-write. The
master is one `dict[str, Any]` living ONLY on the commander, with no replicas:
keys are literal strings, values are opaque. A worker reaches it through
`SpaWorker.global_store`, a `GlobalStoreClient` whose `get`, `set` and `delete`
are CALLs on the lane and whose `for_update` is one turn. Every operation waits
on the same FIFO lock. The turn's `GlobalStoreLease` yields itself with `value`
and `exists`, and its exit sends the COMPLETE value back with `apply=True`.
