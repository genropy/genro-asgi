# Configuration

> **Status:** 🔴 DA REVISIONARE

## What it does

A configuration is a **recipe**: a Python class that writes down what the site is
— the listener, the middleware, the identity surface, the applications — and a
server built from it reads its own values back by path. There is no config file
format to learn: the recipe is code, checked by a grammar that knows which
elements exist and which attributes each one takes.

## When to use it

Use a recipe as soon as the server is more than a demo: it is the one place a
deployment differs, and `genro-asgi serve ./config.py` turns it into a complete
deployment unit (see [the `genro-asgi` command](cli.md)). Keep building the
server by hand — `AsgiServer(applications=[...])` — for a test, a script, or an
embedded server whose objects the recipe cannot express.

## Setup

Nothing to install. `genro_asgi.config` ships `AsgiConfigBuilder` (the dialect
you subclass) and `ConfigurationHandler` (the read door the server builds for
itself); `AsgiServer.grammar` is the grammar they validate against.

## The recipe

A recipe subclasses `AsgiConfigBuilder` and overrides `main(self, root)`. `main`
opens the `configuration` root and delegates each section to its own method,
which takes the **parent node**:

```python
from genro_asgi.config import AsgiConfigBuilder

from myshop.app import Application as Shop


class ServerConfiguration(AsgiConfigBuilder):
    def main(self, root):
        cfg = root.configuration()
        self.server_section(cfg)
        cfg.middleware(cors=True)
        self.applications_section(cfg)

    def server_section(self, cfg):
        """The listener and the session TTL."""
        cfg.server(host="127.0.0.1", port=8000).session(ttl=3600)

    def applications_section(self, cfg):
        """The shop answers the site root."""
        cfg.applications(default="shop").application(
            code="shop", mount="", app_class=Shop
        )
```

Sections are one method each because a section then stays short enough to read
at a glance, and because **the method docstring is where the deployment
explains itself**: the grammar documents what CAN be written, a recipe docstring
documents what THIS instance chose and why. `main` reads as a table of contents.

Every section is a singleton, so its label is its tag and every path below it is
stable and hand-writable: `server.host`, `authentication.oidc.<code>`,
`applications.<code>.parameters.<name>`.

## Values that come from outside: resolvers in place

A value the recipe must not contain — a secret, a per-host address — is stored
as a **resolver where the value would go**, and it resolves at read time, so the
runtime always sees the environment's current value:

```python
from genro_bag.resolvers import EnvResolver


def server_section(self, cfg):
    """Port and storage key belong to the host, not to the recipe."""
    cfg.server(
        host="127.0.0.1",
        port=EnvResolver("SHOP_PORT", dtype="L"),
        storage_key=EnvResolver("SHOP_STORAGE_KEY"),
    )
```

The environment gives strings, so a value that is not a string needs
`dtype=` — `dtype="L"` above delivers a real `int` for `port`. There are no
`^pointer` strings in this dialect: the resolver object itself sits in the
attribute.

For secrets this is not a convention but the signature: `admin_password` takes
`node_value: BagResolver`, so a literal is **rejected at the recipe line** —

```python
cfg.authentication().admin_password(EnvResolver("SHOP_ADMIN_PASSWORD"))
```

— and a resolver that delivers nothing at boot is a `ConfigError`, never a
passwordless SUPERADMIN.

## Handing it to the server

`AsgiServer(config=...)` accepts four sources: a recipe **class**, a recipe
**instance**, a **path** to a `config.py`, or a ready `ConfigurationHandler`.

```python
server = AsgiServer(config=ServerConfiguration)          # class
server = AsgiServer(config="/srv/shop/config.py")        # path
```

An explicit constructor kwarg **wins over the configured value, wholesale per
kwarg** — the server computes nothing, it just prefers what you passed:

```python
tuned = AsgiServer(config=ServerConfiguration, port=9000)
tuned.config("server.port")   # 8000 — the recipe still says what it said
tuned.config_port             # 9000 — what the server will bind
```

## Reading it back

The handler is `server.config` and it is **callable by path**:

```python
server.config("server.host")                  # '127.0.0.1'
server.config("server.session.ttl")           # 3600
server.config("openapi.title", default="Shop API")
```

Each read walks four layers, in order:

1. the **written value** — what the recipe put there;
2. the **element's signature default** — `page_size: int = 20` answers 20 even
   when the recipe never wrote it;
3. the **call-site `default=`** — your fallback for a value nobody declared;
4. a **noisy `KeyError`** naming the path and saying which layers were empty:

```
missing config value 'server.nonexistent' (source: 'configuration.server?nonexistent'):
not written by the recipe, no signature default, no call-site default
```

A server built bare — no `config=` — has `server.config is None`.

## What an application reads

An application holds an **address** in the tree, never a slice of it:
`app.config(path)` prefixes `applications.<code>.` and delegates to the same
door, so the two reads below are the same read.

```python
class Themed(RoutedApplication):
    mount = ""

    @route()
    def theme(self) -> dict[str, str]:
        return {"theme": self.config("parameters.theme", default="light")}
```

```python
site.config("parameters.theme")                          # 'dark'
server.config("applications.site.parameters.theme")      # 'dark'
```

Every application inherits one element, `parameters`, whose kwargs are free —
enough for a handful of options. An app with a real vocabulary of its own
declares a **grammar**, and `application(app_class=...)` mounts it for that
node's children: the site dialect never validates an app's internal words, the
app itself declares them.

```python
from genro_asgi.application import ApplicationGrammar
from genro_builders.builder import element


class ShopGrammar(ApplicationGrammar):
    """The shop's own vocabulary, on top of the inherited ``parameters``."""

    @element(node_label="catalog")
    def catalog(self, title: str = None, page_size: int = 20) -> None:
        """Read back as ``applications.<code>.catalog.<attr>``."""


class Shop(RoutedApplication):
    grammar = ShopGrammar
```

The attributes of the `application` envelope itself (`code`, `mount`,
`app_class`, plus the app's constructor kwargs) belong to the site grammar; only
the children live in the mounted one. An undeclared child is a boot error.

## The sections

One line each; the deep dives live in their own guides.

- **`server`** — `host`, `port`, `external_url` (the PUBLIC address, not the
  listener), `max_threads`, `storage_key`, plus the children `session` (its
  `ttl`) and `tasks` (see [Background tasks](tasks.md)).
- **`middleware`** — one `{name: bool | dict}` switch per middleware; a dict
  enables it and becomes its options (see [Middleware](middleware.md)).
- **`authentication`** — the whole identity surface in one section:
  `admin_password`, the `users`/`tokens` stores, the `login` lockout policy, the
  `oidc` providers and the header `credentials`. The grammar of each is in
  [Authentication](authentication.md).
- **`storage`** — the mounts of the server's `LocalStorage`, one `mount` per
  code, each optionally `encrypted`.
- **`applications`** — the app collection keyed by `code`, with the optional
  `default` naming who `/` redirects to.
- **`databases`** — one descriptor per database: `db_class` and its connection
  kwargs; the core never imports a driver.
- **`plugins`** — the router plugins armed on every routed app.
- **`openapi`** — `title`, `version`, `description` (see
  [OpenAPI & Swagger](openapi.md)).

## A complete recipe

Server, middleware, an environment secret, and one application with a grammar of
its own:

```python
class ServerConfiguration(AsgiConfigBuilder):
    def main(self, root):
        cfg = root.configuration()
        self.server_section(cfg)
        cfg.middleware(cors=True, logging=True)
        self.authentication_section(cfg)
        self.applications_section(cfg)

    def server_section(self, cfg):
        """Bind locally; the public address is what a third party is handed."""
        cfg.server(
            host="127.0.0.1",
            port=EnvResolver("SHOP_PORT", dtype="L"),
            external_url="https://shop.example.com",
            storage_key=EnvResolver("SHOP_STORAGE_KEY"),
        ).session(ttl=3600)

    def authentication_section(self, cfg):
        """The bootstrap secret comes from the environment, never from here."""
        cfg.authentication().admin_password(EnvResolver("SHOP_ADMIN_PASSWORD"))

    def applications_section(self, cfg):
        """One app on the site root, declaring its own catalog block."""
        app = cfg.applications(default="shop").application(
            code="shop", mount="", app_class=Shop
        )
        app.parameters(currency="EUR")
        app.catalog(title="Outlet")
```

## How to verify it

With `SHOP_PORT=8123`, `SHOP_STORAGE_KEY` (a Fernet key) and
`SHOP_ADMIN_PASSWORD` (the bootstrap secret) exported, build the server and
read it back through both doors:

```python
>>> server = AsgiServer(config=ServerConfiguration)
>>> server.config("server.host")
'127.0.0.1'
>>> server.config("server.port")            # resolved, dtype="L" → int
8123
>>> server.config("server.session.ttl")
3600
>>> server.config("middleware.cors")
True
>>> server.config("applications.shop.catalog.page_size")   # signature default
20
>>> shop = server.applications["shop"]
>>> shop.config("parameters.currency")
'EUR'
>>> shop.config("catalog.title")
'Outlet'
>>> shop.config("catalog.locale", default="it")            # call-site default
'it'
```

## Gotchas

- **A secret is a resolver, not a string.** `admin_password` refuses a literal
  in the signature; the other secret-bearing attributes (`storage_key`,
  `client_secret`, `password`, `token`, `secret`) accept one, and should not get
  it — a recipe is code you commit.
- **`dtype=` or you get a string.** `port=EnvResolver("SHOP_PORT")` without
  `dtype="L"` hands the server `"8123"`.
- **`admin_password` needs somewhere to write.** The bootstrap admin lands in
  the identity store, which sits on the `secure` mount — encrypted by
  definition — so a recipe with an `admin_password` and no `storage_key` fails
  at boot with `encrypted mount requires installed keys`.
- **`mount=""` is the site root, and it is not the same as `mount=None`.**
  Omitted, the mount defaults to the `code`; empty, the app answers `/` and every
  unclaimed path.
- **`applications.default` elects nobody.** It names who `/` **redirects to**
  (307) when no application claims the root; naming a code that does not exist is
  a boot error.
- **The recipe is read, not frozen.** A resolver resolves on every read, so
  changing the environment changes what the runtime sees — a configured value
  that looks stale usually means it was copied into a local variable at boot.
- **One recipe class per `config.py`.** The handler's contract is "exactly one
  `ConfigBuilder` subclass in that file"; a second one is an error naming both.
