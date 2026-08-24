# Kubernetes deploy

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The need.** 🔴 PROPOSAL. An installation outgrows one machine. Kubernetes creates, isolates, runs and observes the containers — but the commander keeps EVERY applicative decision: how many workers, who lives where, which version gets traffic. No HPA, no second scheduler.

From `codex/architettura-gruppi-uv-subcommander-kubernetes-2026-08-19.md`:
worker Pods with `restartPolicy: Never` (a death is a fact the commander
observes and answers), outbound presentation to the commander, fencing by
`worker_handle` + `generation`, images built with UV at build time, a shared
freezer backend (Redis candidate) for cross-node mobility. Phases K0–K6.

Interactions: orchestration (the commander stays the only policy owner) · deployment-bundles (immutable images/bundles) · subcommanders (the hierarchy, when it comes).
