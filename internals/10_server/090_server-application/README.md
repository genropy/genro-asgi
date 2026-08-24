# Server application (`_server`)

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

The one place where the server itself is administered: the `_server` app every
server mounts without anyone configuring it. It hosts the admin surfaces as
sections — auth, users, tokens, tasks, monitor, inspector — gated by the
`SERVER_ADMIN` permission.
