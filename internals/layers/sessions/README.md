# Sessions

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The shelf.** Per-user server-side state between requests, and its persistence.

The server-side session: `MemoryStore`, delta-check persistence, pickle
snapshot per named instance (`serve --name`), cookie `Max-Age = ttl × 24`,
the avatar.

Interactions: middleware (session) · authentication.
