# Lifecycle and shutdown

> **Status:** Draft; implementation checked against the development source on 2026-09-08.

Application `on_startup` hooks run in registration order; `on_shutdown` hooks
run in reverse. Either hook may be synchronous or asynchronous. Synchronous
hooks run directly on the event-loop thread, so keep them short or explicitly
offload blocking work. Ordinary hook exceptions are logged and the sequence
continues. Raise `genro_asgi.lifespan.FatalBootError` from startup when a missing
prerequisite must prevent the server from starting.

```python
from genro_asgi import RoutedApplication
from genro_asgi.lifespan import FatalBootError


class Catalog(RoutedApplication):
    async def on_startup(self):
        if self.config("parameters.catalog_url", default=None) is None:
            raise FatalBootError("Configure parameters.catalog_url")

    async def on_shutdown(self):
        pass  # close application-owned resources here
```

This is a hook fragment, not a running catalog service. Supply its configuration
and routes before serving it.

## Admission and draining

The server begins with state `RUNNING`. Lifespan shutdown changes it to
`shutdown_mode` (normally `STOPPING`; the reload child uses `QUITTING`) before
waiting for in-flight registered requests, then runs the application hooks.
The registry drain has its own finite timeout. Requests reaching core HTTP
dispatch while not running receive 503 with `Retry-After` and are not registered.
Middleware that answers on its own can still answer before that gate.

New WebSocket handshakes are refused before accept whenever the server is not
running, including raw WebSockets. A browser sees a failed handshake rather than
a readable post-accept close code. See [WebSockets](websockets.md).

`shutdown_timeout_seconds` defaults to **5.0** and controls uvicorn's wait for
open connections before cancelling them, allowing lifespan shutdown to run even
when an HTTP stream never ends:

```python
from genro_asgi.config import AsgiConfigBuilder


class Configuration(AsgiConfigBuilder):
    def main(self, root):
        root.configuration().server(shutdown_timeout_seconds=5.0)
```

The same value can be passed to `AsgiServer(shutdown_timeout_seconds=5.0)`.
This is a connection-drain timeout, not a five-second deadline for the entire
process: application hooks and worker shutdown have their own work to finish.
Stop a foreground server with Ctrl-C; the CLI's `stop` sends SIGTERM to the
named server (or reload supervisor). See [CLI](cli.md).
