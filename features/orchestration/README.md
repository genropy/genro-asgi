# Orchestration

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

The pool machine: `SpaCommander` (global indexes, lifecycle, per-user
barrier, request chain, single-writer fold via `EnvelopeHandler`, freezer
via `FreezeHandler`, `DeliveryDesk`) → n `GroupHandler` (placement,
capacity, growth and shrink) → n `WorkerHandler` (process, wire,
surveillance) → `SpaWorker` (live users/connections/pages and the hosted
WSGI site behind `WsgiSeam`). Usersticky principle: ALL pages of one user
live in the process that holds the user's store. Mobility has ONE path:
hold → freeze → reassign → unfreeze. A sudden worker death restarts the
few users involved — an accepted, observable risk.

Interactions: spa-application (above) · channel (below) · global-store, datachanges, dbevents (it carries them) · storage (freezer) · restart.
