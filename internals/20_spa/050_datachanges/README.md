# Datachanges distribution

**Version**: 0.1 · **Last Updated**: 2026-09-02 · **Status**: 🔴 DA REVISIONARE

What one page changes, the pages that care must see, without any page polling
the world. A page's own queue lives on its register row and empties on the
worker, and delivery is ADDRESSED through the `DeliveryDesk` — never broadcast,
never per-worker snapshots.
