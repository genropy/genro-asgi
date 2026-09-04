# Bridge contract

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The need.** genropy-asgi is the first customer: it must run legacy GenroPy sites on this core WITHOUT the core learning GenroPy's logic. The bridge implements a contract; the core offers generalized mechanisms.

What the hosted site must provide and what it may consume: the WSGI
callable behind `WsgiSeam`; the site names its OWN connection while serving
(the `spa_connection_id` identity decision, 2026-08-22); what the bridge pins
(frozen tag v0.35.0) until migrated to this core. NO release of genro-asgi
from develop until this contract is honoured by a migrated bridge.

The site's own data plane — datachanges, dbevents, table subscriptions, the
user view — is the bridge's since #59 (2026-09-04), attached through the seams
the core names, composition never a subclass of the worker or the vertex:

- `SpaApplication.commander_class`: the bridge's subclass of `SpaCommander`.
- `SpaCommander.commander_dispatcher.add_branches(...)`: the bridge's own
  operations under `/commander/<name>/…`, called by the worker up the lane.
- `SpaWorker.worker_dispatcher.commander_orders.add_branches(...)`: the
  bridge's own orders to the worker, called by the vertex down the lane.
- `SpaCommander.on_worker_presented(worker_handler)`: a process has just
  presented itself — where the bridge pushes what a newborn must know.
- `SpaCommander.envelope_handler` (property): the last layer of the envelope
  chain; the bridge returns its subclass of `CommanderEnvelopeHandler` and reads
  in its own `on_<op>`, after the core's, what a worker event carries for it —
  the tables a newborn page subscribes, above all.
- `SpaWorker.build_request_slot()` / `on_request_served()`: what a request
  carries, and the tail of every served request.
- `RegisterRegistry.page_row_class` + `subscribe_page_store` / `detach_page` /
  `new_store`: the bridge's row fields, its capture, its store type.
- `SpaCommander.new_global_store()` / `apply_global_store_changes()`: the
  vertex's data, a type the TYTX codec knows.

Interactions: spa-application (the cookie) · orchestration (the worker that hosts, the two dispatchers) · global-store (the verbs).
