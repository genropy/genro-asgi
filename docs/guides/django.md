# Django on the multiworker pool

> **Status:** Draft; implementation checked against the development source on 2026-09-12.

## What it does

Serves a Django project through the SPA pool: a group of worker processes, one
of which holds each browser session and keeps holding it. Django's own WSGI
callable is the hosted application, and the connection the pool routes on is
Django's session.

## When to use it

When the project keeps state in the process — a cache-backed or in-memory
session, an expensive per-session object — and every request of one browser
must come back to the process that holds it. A stateless Django project does
not need the pool.

## Setup

Two classes, in the `genro_asgi_django` package, named by the recipe as dotted
paths:

| Class | Role |
|---|---|
| `genro_asgi_django.worker:DjangoWorker` | the worker: it hosts Django and declares the connection |
| `genro_asgi_django.engine_factory:DjangoEngineFactory` | the group's template: one `django.setup()`, every worker a fork of it |

Both take the same two words: `settings_module`, the dotted path written into
`DJANGO_SETTINGS_MODULE`, and `project_path`, the directory the project's own
packages are imported from. The second is needed because the template and the
workers are children started with `python -m`: they inherit the server's
environment and not its `sys.path`.

Django itself is not a dependency of `genro-asgi`; importing
`genro_asgi_django` imports Django.

## Minimal snippet

The whole recipe — `contrib/django/examples/hello_world/config.py`:

```python
import os

from genro_asgi.config import AsgiConfigBuilder
from genro_asgi_multiworker_spa.spa_app import SpaApplication

PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT = {"settings_module": "hello_site.settings", "project_path": PROJECT_PATH}


class ServerConfiguration(AsgiConfigBuilder):
    def main(self, root):
        cfg = root.configuration()
        cfg.server(host="127.0.0.1", port=8131)
        cfg.middleware()
        front = cfg.applications().application(
            code="hello", mount="", app_class=SpaApplication
        )
        commander = front.orchestration().commander(
            frozen_users_path="/tmp/gnrasgi_django_hello/frozen_users",
            instance_dir="/tmp/gnrasgi_django_hello",
        )
        commander.groups().group(
            name="pool",
            entry_module="genro_asgi_multiworker_spa.orchestration.worker_entry",
            worker_class="genro_asgi_django.worker:DjangoWorker",
            worker_kwargs=PROJECT,
            engine_factory="genro_asgi_django.engine_factory:DjangoEngineFactory",
            engine_kwargs=PROJECT,
        )
```

The example project next to it has one view, no database, and its session in
the process's own memory (`SESSION_ENGINE` on the `locmem` cache). The view
counts the visits of its session, which is what makes the stickiness visible.

## How to verify it

```
cd contrib/django/examples/hello_world
genro-asgi serve ./config.py
curl -D - -c jar -b jar http://127.0.0.1:8131/
curl -c jar -b jar http://127.0.0.1:8131/
```

The first answer carries two cookies with the same value — Django's
`sessionid` and the pool's `spa_connection_id` — and `visits: 1`; the second
answers `visits: 2`, which it can only do from the process that holds the
session.

With `GNR_ASGI_INSPECTOR=1` set and a `ServerApplication` mounted as `_server`
(the example mounts it under the same condition), `GET
/_server/inspector/census` shows the connection under its worker:

```json
"connection_user_map": {"<session key>": "guest_<session key>"},
"groups": {"pool": {"user_worker_map": {"guest_<session key>": "pool_0001"}}}
```

## How the connection is declared

`DjangoWorker.serve_django` calls Django and watches the answer's headers. The
session key comes from the `Set-Cookie` of a session Django has just minted, or
from the `Cookie` the request came in with; the worker calls `new_connection`
with it the first time this process sees it. The core stamps that id on the
request's slot, the reply carries it back, and the front writes it in the
`spa_connection_id` cookie — one identity space, the site's own.

## Gotchas

- **A request that writes nothing to the session declares no connection.**
  Django mints a session key only when the session is touched, and a request
  with no session has nothing to be sticky to.
- **No user, for now.** The worker declares the connection and never the user:
  who the user is, is what Django knows at login, and telling the worker
  (`change_connection_user`) is separate work.
- **A database-backed session works too**, and then the stickiness matters
  less: the point of the pool is the state the process holds.
- **The worker serves Django on the traffic pool**, so the project must be
  thread-safe in the ordinary WSGI sense — nothing new, but the process serves
  several sessions at once.
- **One body in, one body out.** The worker path buffers the whole request and
  the whole response: streaming uploads, downloads and SSE do not go through it
  (see [Multiworker SPA](multiworker-spa.md)).
