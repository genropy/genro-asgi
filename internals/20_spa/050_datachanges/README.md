# Datachanges distribution

**Version**: 0.1 · **Last Updated**: 2026-09-03 · **Status**: 🔴 DA REVISIONARE

What one page changes, the pages that care must see, without any page polling
the world. A page's own queue lives on its register row and empties on the
worker, and delivery is ADDRESSED through the `DeliveryDesk` — never broadcast,
never per-worker snapshots. An addressed write at a page of the caller's own
user on this worker is appended to that page's row directly; every other address
leaves at once as one CALL to the desk.
