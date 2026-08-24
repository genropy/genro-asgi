# Tasks

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

Work that is no HTTP request: schedules, batches and spooled runs that survive
and are accounted for. The scheduler holds the cron-like plans, the spool is the
on-disk truth of every run, and the executor and manager drive them; the
subsystem mounts like any other app and is administered through the
`_server/tasks` section.
