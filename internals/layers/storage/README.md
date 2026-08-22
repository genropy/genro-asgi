# Storage

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The shelf.** The only door to the filesystem: logical volumes, storage nodes, pinned synchronous.

Filesystem access goes ONLY through storage nodes: logical volumes
(`GENROASGI:frozen_users`), pinned synchronous (D22 — `StorageMixin` calls
`set_sync()`; never `await` a storage node here).

Interactions: orchestration (freezer parcels) · sessions (snapshots) · tasks (spool).
