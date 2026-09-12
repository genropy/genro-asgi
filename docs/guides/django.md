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

Beside them, one line the project adds to its own `MIDDLEWARE` when it wants
the pool to know who logged in — see [Who logged in](#who-logged-in).

Both take the same two words: `settings_module`, the dotted path written into
`DJANGO_SETTINGS_MODULE`, and `project_path`, the project directory — what
`manage.py` sits in. The second is needed because the template and the workers
are children started with `python -m`: they inherit the server's environment and
not its `sys.path`. `project_path` also becomes the **working directory** of the
template process, and therefore of every worker forked from it, because a real
project settles relative settings against it: Wagtail's bakerydemo writes
`TEMPLATES[0]["DIRS"] = ["bakerydemo/templates"]`, which resolves only when the
process stands where `manage.py` does.

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

The example project next to it has three views, no database, and its session in
the process's own memory (`SESSION_ENGINE` on the `locmem` cache). `/` counts
the visits of its session, which is what makes the stickiness visible, and
`/login/` and `/logout/` run Django's own `login` and `logout` against two
literal users (`hello_site/auth.py`), so the whole cycle is there without a
database.

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

## Who logged in

Until the login, the pool knows a connection and calls its owner
`guest_<session key>`. Who the user IS, is a fact of Django's session, and
Django says so through one line in the project's `MIDDLEWARE`:

```python
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "genro_asgi_django.middleware.UserStickyMiddleware",
]
```

It goes **below** those two: it reads the session, and the user they put there.

What it watches is `_auth_user_id`, the one thing `django.contrib.auth.login`
and `logout` write in and take out of the session, read once before the request
is served and once after. Its appearance is a login and the middleware calls
`DjangoWorker.declare_user` with the session key and the username; its
disappearance is a logout and the middleware calls
`DjangoWorker.retire_connection`, which takes the connection off the worker —
the core has no way back to nobody, because `change_connection_user` refuses a
guest as a target. A different value is an avatar switch and reads as a login.

The middleware reaches the worker through the environ: `DjangoWorker` puts
itself under `genro.spa_worker` while it serves, beside the core's
`genro.identity`. An environ with no worker in it is the same project under
`manage.py runserver`, and there the middleware does nothing at all.

From the login on, the user is what the pool places, freezes, transfers and
shuts down in order: every connection of one user lives in one process.

### What it looks like

Wagtail's bakerydemo, `admin` logging in through its own form. The answer of
the login POST carries the new session, and the pool's cookie with it:

```
HTTP/1.1 302 Found
location: /admin/
set-cookie: sessionid=ef8el336xz7sn4ntc6lsdsurdlrv76ei; HttpOnly; Path=/
set-cookie: spa_connection_id=ef8el336xz7sn4ntc6lsdsurdlrv76ei; Max-Age=86400; Path=/
```

and the census answers with a user where it used to answer with a guest:

```json
"connection_user_map": {"ef8el336…": "admin"},
"user_worker_map": {"admin": "pool_0001"}
```

A second browser logging in as the same `admin` is a second connection on the
same worker. A logout takes its own connection away, and the last logout takes
the user with it.

## A real site

`contrib/django/examples/bakerydemo/` serves Wagtail's demo bakery — the admin,
login and logout, sessions, a SQLite database, images, static files and search —
on the same recipe shape, pointing at a checkout you make yourself outside this
repository. Its README carries the four commands. What it needed beyond the
hello world was one thing: the working directory, described under Setup.

## Gotchas

- **A request that writes nothing to the session declares no connection.**
  Django mints a session key only when the session is touched, and a request
  with no session has nothing to be sticky to.
- **Without the middleware line there is no user.** The worker declares the
  connection from the session cookie and nothing else; a project that does not
  add the line keeps a pool of guests, which is a usable shape — the stickiness
  is the connection's.
- **A logout leaves the cookie behind.** The pool's own rule is that a
  connection id stays in `connection_user_map` (`SpaCommander.drop_connection`:
  "the cookie is eternal"), so a browser that logged out still presents a
  `spa_connection_id` the front routes as its old user until that user's LAST
  connection goes. It costs nothing: Django has deleted its `sessionid` and
  answers the request as anonymous. Identity is Django's decision; the pool only
  routes.
- **The login cycles the session key.** `django.contrib.auth.login` mints a new
  one, so the connection the pool owns after a login is not the one it owned
  before, and the old row is left to the idle valve.
- **A database-backed session works too**, and then the stickiness matters
  less: the point of the pool is the state the process holds.
- **The worker serves Django on the traffic pool**, so the project must be
  thread-safe in the ordinary WSGI sense — nothing new, but the process serves
  several sessions at once.
- **Static and media are the project's business.** With `DEBUG` on, Django's
  own urlconf serves `/static/` and `/media/` and they come through the pool
  like any other view; with `DEBUG` off they are served the way they would be
  behind any WSGI server, and the pool changes nothing about that choice.
- **One body in, one body out.** The worker path buffers the whole request and
  the whole response: streaming uploads, downloads and SSE do not go through it
  (see [Multiworker SPA](multiworker-spa.md)).
