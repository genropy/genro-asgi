# Orchestration — decisions

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

## Seeded ahead of the audit — the template process and the fork birth

**Source: commits `7714f53`, `915133f`, `00f236e`, `e1091f0`, `8dc45d7`,
`adddd29` (2026-08-24). Implemented; not yet audited.** A group whose recipe
declares `engine_factory` (`module:Class`, with `engine_kwargs`) owns a
**template process** — `template-<group>`, spawned by its `GroupHandler`,
running `template_entry.py`:

- the template builds the **group engine** once — the expensive thing every
  worker of the group shares — freezes its heap before the first fork, and
  from then on **every worker of the group is a `fork` of the template**: the
  engine is not rebuilt and not copied, the children find it in their own
  memory;
- the template is **synchronous by design**: a child forked out of a running
  asyncio loop inherits it as running over a shared epoll — a whole class of
  trouble deleted rather than worked around;
- everything travels as **JSON lines on the pipes**, nothing in environment
  variables; a short first line is a contract violation;
- `WorkerEntry` accepts the inherited `group_engine` and hands it to the
  `SpaWorker`; a `WorkerHandler` asks its process the same two questions
  whatever its birth (`worker_process.py` — spawn and fork answer alike);
- a group **without** the factory spawns workers the ordinary way and has no
  template at all — a composition difference, not a flag.

---

# Open frictions

Scaffolding for the interview, not a register: each voice is a question to
settle, settling it edits this document, and this section shrinks to nothing
before the design can be ratified.

*(Carried over from the entry's former `frictions.md` on 2026-08-23, verbatim.)*

- F48/F49: a fold that fails in the parent no longer kills the worker, but the partially applied envelope has no escalation/resync yet; the two decisions are cited by code and commits and still missing from the F1–F47 register.
