# Subcommanders

**Version**: 0.1 · **Last Updated**: 2026-09-08 · **Status**: 🔴 DA REVISIONARE

**The need.** 🔴 PROPOSAL. One commander cannot own the whole world at scale. Delegated authorities — root → subcommander → group → worker — each own their domain: the root holds the user→branch directory and budgets, the subcommander holds its groups and placement.

From the unratified proposal
`codex/architettura-gruppi-uv-subcommander-kubernetes-2026-08-19.md`
(2026-08-19): one policy owner per resource, budgets
granted downward, transfer between subcommanders through the shared freezer
with epochs (hold → freeze → release ownership → reassign → adopt), lease
and fencing so no stale authority ever comes back. The meaning of a
subcommander (shard, node, zone, tenant, application) is deliberately
undecided.

Interactions: orchestration (recursive extension of its ownership model) · kubernetes-deploy (the runtime it commands) · global-store and the desks (must learn hierarchy).
