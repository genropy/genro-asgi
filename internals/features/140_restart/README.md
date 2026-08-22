# Soft and hard restart

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The need.** The server must be restartable — urgently or gently — without betraying the people working on it at that moment.

Stopping and restarting a living server without losing what must
survive: the restart liturgy (hard/soft at the decider's choice, notice via
notify_user, delegation to ServerApplication, execv) and `dump`/`restore`
across a full server restart. SECOND PASS: none of it is built on develop.

Interactions: orchestration (park everybody, refill) · sessions (their snapshot exists already) · global-store (explicitly NOT restored — owner decision 2026-08-22).
