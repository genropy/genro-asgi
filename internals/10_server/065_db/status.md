# Database — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## Mounted database handlers

The recipe's `database` names `db_class` and optionally `db_handler_class`.
`AsgiServer._register_configured_databases` builds the database from resolved
parameters, wraps it in the handler (default `AsgiDbHandlerBase`) and registers
it by code. Duplicate codes raise `ValueError`. Concrete backends remain
consumer code.

`AsgiDbHandlerBase` delegates non-private attributes and calls the wrapped
`closeConnection` when present. `Request.db` resolves the application's
`db_name` or `default`, caches the handler and registers cleanup on the current
request item. `get_db(name)` performs lookup without registering that cleanup.
Thread-affine consumer cleanup is separately available in
`RoutedApplication.route_cleanup`.

Claim anchors: [`db`](../../../src/genro_asgi/request.py#L374), [`AsgiServer`](../../../src/genro_asgi/asgi_server.py#L91), [`_register_configured_databases`](../../../src/genro_asgi/asgi_server.py#L180), [`AsgiDbHandlerBase`](../../../src/genro_asgi/db.py#L37), [`closeConnection`](../../../src/genro_asgi/db.py#L49), [`Request`](../../../src/genro_asgi/request.py#L107), [`db_name`](../../../src/genro_asgi/routed_application.py#L142), [`get_db`](../../../src/genro_asgi/request.py#L400), [`RoutedApplication`](../../../src/genro_asgi/routed_application.py#L111), [`route_cleanup`](../../../src/genro_asgi/routed_application.py#L261).

## Source and test evidence

- [src/genro_asgi/db.py](../../../src/genro_asgi/db.py)
- [src/genro_asgi/asgi_server.py](../../../src/genro_asgi/asgi_server.py)
- [src/genro_asgi/request.py](../../../src/genro_asgi/request.py)
- [src/genro_asgi/routed_application.py](../../../src/genro_asgi/routed_application.py)
- [tests/core/test_db.py](../../../tests/core/test_db.py)
- [tests/core/test_request.py](../../../tests/core/test_request.py)
- [tests/core/test_config.py](../../../tests/core/test_config.py)
