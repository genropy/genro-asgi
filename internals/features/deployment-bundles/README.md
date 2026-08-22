# Dynamic groups and application bundles

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The need.** A customer tries a change with named users while production runs untouched; the build they accepted is promoted AS IS, never rebuilt.

🔴 UNRATIFIED PROPOSAL (from `codex/`): groups as dynamic runtime
objects — add / refresh / remove while the server lives — each pinned to an
immutable application bundle built by the application's own CI and
distributed through S3 (named builds, mutable channels, explicit cohorts
for iterative acceptance). Horizon: subcommander hierarchy and Kubernetes
as controlled runtime.

Interactions: orchestration (GroupHandler lifecycle) · configuration (group grammar) · restart (generation switch).
