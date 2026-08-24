# Global store

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

One state shared across every user and page, with a safe read-modify-write. The
master Bag lives ONLY on the commander, with no replicas: a worker reads with a
call on the lane, and writes through the lock, whose grant carries the true
master state and whose release applies exactly what the holder drained.
