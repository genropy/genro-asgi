## Phase 1

- The `Done:` grep lists "commander census" among the files naming `cpu_heating_seconds`.
  The census carries the VALUES (`cpu_temperature_percent`, `cpu_temperature_sample_percent`),
  never the setpoint's name, so `spa_commander.py` cannot appear in that grep. Read as:
  policy, grammar, `config/handler.py`, `group_handler.py`, `worker_handler.py`, the three
  docs — all found; the census is asserted by the meter test instead.
- `test_fresh_temperature_closes_and_reopens_cpu_admission` changed meaning on purpose:
  one idle 100 ms sample no longer reopens a worker at 80% (it cools it to ~78.4%); five
  seconds of silence do. That is the defect measured on `temp4`.
- The indentation of `cpu_temperature_sample_seconds` in the commander grammar signature
  (`spa_app.py`) was wrong by four spaces; fixed in passing, same file.
- The census test double in `test_orchestration_census.py` gained the new attribute.
