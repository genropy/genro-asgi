# Inspector — decisions

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

Owner direction (2026-08-22): the inspector starts by showing ONLY the
server's own structures; every application can be CALLED to contribute its
own inspect panel — the same contribution-contract style the monitor
already uses (`app_snapshot`/`app_panel`/`panel_source`). The SPA
enrichment lives in the SPA application, never in the section.

---

# Open frictions

Scaffolding for the interview, not a register: each voice is a question to
settle, settling it edits this document, and this section shrinks to nothing
before the design can be ratified.

*(Carried over from the entry's former `frictions.md` on 2026-08-23, verbatim.)*

- The current implementation contradicts the contribution contract:
  `inspector_section.py:48` imports `SpaApplication` and `isinstance`-checks
  the mounted apps — SPA knowledge hardwired into a server section.
