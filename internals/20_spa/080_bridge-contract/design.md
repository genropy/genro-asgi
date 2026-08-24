# Bridge contract

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The need.** genropy-asgi is the first customer: it must run legacy GenroPy sites on this core WITHOUT the core learning GenroPy's logic. The bridge implements a contract; the core offers generalized mechanisms.

What the hosted site must provide and what it may consume: the WSGI
callable behind `WsgiSeam`; the site names its OWN connection while serving
(the `spa_connection_id` identity decision, 2026-08-22); the data-plane
verbs of the site↔worker seam; what the bridge pins (frozen tag v0.35.0)
until migrated to this core. NO release of genro-asgi from develop until
this contract is honoured by a migrated bridge.

Interactions: spa-application (the cookie) · orchestration (the worker that hosts) · datachanges/dbevents/global-store (the verbs).
