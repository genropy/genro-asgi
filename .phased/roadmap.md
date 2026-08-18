# Roadmap — SPA orchestration rebuild

Authority order, most recent first — on a conflict the most recent wins:

1. `temp/design_m4_2026-08-18.md` — the Macro 4 decision record (🟢 APPROVATO,
   R1..R14);
2. `temp/design_orchestrazione_v4_2026-08-17.md` — design v4;
3. `temp/design_orchestrazione_v3_2026-08-16.md` — design v3, for the sections
   v4 does not touch (§8 freezer, §9 data plane, §11 login, §12 boot, §13
   observability, §14–15);
4. `temp/interview_handler_2026-08-15.md` — the decision register (D1-D10, A,
   B/C/D/E, F1–F47), for what the three above do not cover.

- Macro 1: Foundations — FreezeHandler (deposit), WorkerConnector
  + per-WorkerHandler UDS endpoint, WorkerHandler/LocalWorkerHandler with
  low-tolerance surveillance — detailed in
  active/orchestration-m1-foundations/plan.md as Phases 1..4.
- Macro 2: The new worker process — user rows active/frozen/unfreezing,
  two thread pools (traffic vs service), async freeze cycle, adoption
  (verdict + connection self-service), time-throttled photo, the three
  activity clocks and the ping rules. Needs Macro 1.
- Macro 3: GroupHandler + Commander — group map, capacity-aware placement
  with 503 + immediate wake growth, metronome with separated cadences,
  fold + indexes, mailbox + broadcast dictionary, elimination/cassation/
  sweeper, vertex parking, orchestration log, in-memory global store,
  need_resources. Needs Macro 2.
- Macro 4 (current): The request chain and login — the vertex's request
  chain, the login verb and its uniform fold, and a NEW front ALONGSIDE the
  legacy one (R1, `temp/design_m4_2026-08-18.md`); cutover at Macro 6.
  Detailed in active/orchestration-m4-request-login/plan.md as Phases 1..5.
  Needs Macro 3.
- Macro 5: The data plane, startup/shutdown and observability — addressed
  datachanges/dbevents, subscriptions, the pending mailboxes
  (USER_PENDING_MAX_ITEMS), notifications and broadcast, the global store
  lock grant; hard/soft boot with the reboot-directory liturgy (per-group
  folders, inner .lock), the shutdown channel doctrine, dev-reload auto-soft,
  monitor panels, _server/prometheus metrics. Also the machinery that still
  lives only in the legacy: the live move, the plan's ladder,
  recycle_worker, hard_restart, dump/restore, the in-process worker.
  Needs Macro 4.
- Macro 6: Cutover and cleanup — the real traffic moves onto the new front,
  the legacy machine (spa/commander.py, spa/worker.py,
  applications/spa_app.py) and its contract sentinels die together, dead code
  removed (design v3 §14), test reclassification, documentation (the "How it
  works" section of CLAUDE.md becomes the new machine's). Needs Macro 5.
