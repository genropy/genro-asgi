# Roadmap — SPA orchestration rebuild (design v3)

Spec of record: `temp/design_orchestrazione_v3_2026-08-16.md` (design v3,
implementation grade). Decision log with the owner's ratifications:
`temp/interview_handler_2026-08-15.md` (D1-D10, A, B/C/D/E, F1-F39).

- Macro 1 (current): Foundations — FreezeHandler (deposit), WorkerConnector
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
- Macro 4: The request chain and login — SpaApplication wired to the new
  Commander, end-to-end chain, cutover from the legacy commander. Needs
  Macro 3.
- Macro 5: Startup/shutdown and observability — hard/soft boot with the
  reboot-directory liturgy (per-group folders, inner .lock), the shutdown
  channel doctrine, dev-reload auto-soft, monitor panels,
  _server/prometheus metrics. Needs Macro 4.
- Macro 6: Cleanup — remove the dead code (design v3 §14), test
  reclassification, documentation. Needs Macro 5.
