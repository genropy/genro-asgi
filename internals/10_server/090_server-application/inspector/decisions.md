# Inspector — decisions

**Version**: 0.2 · **Last Updated**: 2026-09-07 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

Owner direction (2026-08-22): the inspector starts by showing ONLY the
server's own structures; every application can be CALLED to contribute its
own inspect panel — the same contribution-contract style the monitor
already uses (`app_snapshot`/`app_panel`/`panel_source`). The SPA
enrichment lives in the SPA application, never in the section.

Owner decision (2026-09-07, workflow `core-spa-boundary` phase 3): the
section itself left the server sections. It lives in
`genro_asgi_multiworker_spa/inspector_section.py`, its parent is the `SpaApplication`
that attaches it on startup under `GNR_ASGI_INSPECTOR`, and it reads that
front's own pool through `self.application.commander`. A server has ONE
orchestrated application, so a second attach is a `FatalBootError`.

**This settles the friction below, and not by the contribution contract the
2026-08-22 direction imagined.** The contract answers "how does a server
section learn about an application it must not know"; moving the section out
of the server dissolves the question — there is no server section left to
teach. The direction stands for the sections that DO stay in the core: the
monitor is the one that uses it. Whether the inspector should later grow
per-application panels through that contract is open, and is now a question
about a SPA-world surface, not about `_server`.

---

# Open frictions

Scaffolding for the interview, not a register: each voice is a question to
settle, settling it edits this document, and this section shrinks to nothing
before the design can be ratified.

*(Carried over from the entry's former `frictions.md` on 2026-08-23, verbatim.)*

- ~~The current implementation contradicts the contribution contract:
  `inspector_section.py:48` imports `SpaApplication` and `isinstance`-checks
  the mounted apps — SPA knowledge hardwired into a server section.~~
  Settled 2026-09-07: the section moved to the SPA world, the `isinstance`
  loop is gone, and `SpaApplication` is named under `TYPE_CHECKING` only.
