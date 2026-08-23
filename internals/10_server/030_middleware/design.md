# Middleware — desired design

**Version**: 0.2 · **Last Updated**: 2026-08-23 · **Status**: 🔴 DA REVISIONARE

Everything this feature SHOULD be when finished — the target, not the code.
To be filled by the documentation audit and ratified by the owner.

---

# Open frictions

Seeded before this entry is audited, by a friction found in a neighbouring one
and written here in the same words. It is settled once for both.

**S1 — two exception-to-status mappings, and nothing relates them.** The route
resolution maps router failures to the HTTP exceptions the ring answers. The
response class carries a second table of its own, which maps `ValueError` and
`TypeError` to 400, `FileNotFoundError` to 404, `PermissionError` to 403 and
everything else to 500. Both exist; no document says which applies when, or
whether the second is the mechanical cause of the sync-handler `TypeError`
reported to the caller as a bad request. The division of labour has to be
stated, and this entry owns the ring. Recorded in the same wording in
[020 applications](../020_applications/design.md), friction S14.
