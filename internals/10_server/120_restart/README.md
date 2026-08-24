# Soft and hard restart

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

A living server is stopped and restarted — urgently or gently — without
betraying the people working on it at that moment: the restart liturgy (hard or
soft at the decider's choice, notice to the users, delegation to
`ServerApplication`, `execv`) and `dump`/`restore` across a full restart.
Restart is born here, and each world above enriches it through its own
mechanisms.
