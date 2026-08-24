# Storage

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

The only door to the filesystem. Access goes through storage nodes on logical
volumes, and it is pinned synchronous: `StorageMixin` calls `set_sync()`, and a
storage node call here is never awaited.
