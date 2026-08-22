# SPA application (the front)

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

The stateless door of the SPA world: the `spa_connection_id` cookie
carrying the hosted site's OWN connection id (the front mints nothing),
the two-stage demux (internal roots vs the hosted site), and the HTTP
translation of the pool's answers — 503 with `Retry-After` for a refusal,
502 for a site failure, generic lines outward and the real text in the log.

Interactions: orchestration (`SpaCommander.serve_request` is the single forward) · configuration (grammar) · inspector/console.
