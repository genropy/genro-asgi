# Task thermometers (termometri)

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

The live progress of a running batch: `TaskManager.publish_progress`
writes the `progress.json` snapshot on the spool AND publishes the same
data on the live event channel in one paired call, so a page shows the bar
while it moves. Cooperative interruption: the stop request is a signal the
batch reads at its own pace, and the intermediate 'stopping' state stays
visible.

Interactions: tasks (spool = source of truth) · SSE/event hub (the live courier).
