# Server application (`_server`)

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

The automatic system app every server mounts. It hosts admin surfaces as
*sections* (auth, users, tokens, tasks, monitor, inspector), gated by the
`SERVER_ADMIN` permission with the house rule: 401 to the anonymous, 403 to
the known.

Interactions: monitor · inspector · tasks · authentication.
