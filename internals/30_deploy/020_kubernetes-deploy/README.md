# Kubernetes deploy

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

🔴 Unratified proposal. An installation outgrows one machine: Kubernetes creates,
isolates, runs and observes the containers, and the commander keeps EVERY
applicative decision — how many workers, who lives where, which version gets
traffic. Worker Pods with `restartPolicy: Never`, outbound presentation to the
commander, fencing by `worker_handle` and `generation`, and a shared freezer
backend for cross-node mobility.
