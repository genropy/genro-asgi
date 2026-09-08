# Global store — decisions

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

## Record boundary — 2026-09-08

This decision register is still a scaffold. The September contract and its
claimed owner decisions currently live in [design](design.md) and
[status](status.md); the source and test links in status verify implementation,
not ratification. Their presence does not make this register complete. The
renewal preserves that material without manufacturing an approval transcript;
consolidating each decision with its exact owner provenance remains open.

## Exact ratification gaps

- **Typed-looking strings:** design calls leaving `"42::L"` unescaped an
  “owner decision”. The exact owner instruction approving this loss of string
  round-trip fidelity has not yet been recovered. Current codec behavior and
  issue #74 delivery alone do not ratify acceptance of that limitation.
- **Lease contract:** the design specifies a commander-only dictionary, one
  global lock including reads, literal keys, selected-key/full-dictionary
  leases, abort without apply, worker-death release, and an unconfirmed-commit
  error without blind retry. Source/tests establish that these are delivered
  contracts; dated owner provenance for approving this complete target still
  needs to be consolidated here.
- **Legacy datetime boundary:** design assigns adaptation to genropy-asgi.
  Preserve this allocation as written, with exact approving provenance still
  to be recovered rather than inferred from the core implementation.
