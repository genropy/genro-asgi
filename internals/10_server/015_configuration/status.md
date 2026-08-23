# Configuration — current state

**Version**: 0.2 · **Last Updated**: 2026-08-23 · **Status**: 🔴 DA REVISIONARE

What exists TODAY on `develop`. Every claim carries its `file:line` or the test
that proves it. Coverage from the full suite (`pytest tests/`, 1463 passed) run
on 2026-08-23 at `4a2eceb`.

## The modules

| Module | Lines | Stmts | Miss | Cov |
|---|---|---|---|---|
| `src/genro_asgi/config/handler.py` | 406 | 147 | 0 | 100% |
| `src/genro_asgi/config/elements.py` | 370 | 52 | 0 | 100% |
| `src/genro_asgi/config/default_config.py` | 133 | 48 | 1 | 98% |
| `src/genro_asgi/config/builder.py` | 133 | 26 | 0 | 100% |
| `src/genro_asgi/config/__init__.py` | 40 | 5 | 0 | 100% |

The one uncovered statement is `default_config.py:117` — the `ConfigError`
raised when a `config.py` cannot be imported at all (a broken import spec), the
only branch of `recipe_class` no test drives.

The dialect is not written here: it is `genro_builders.contrib.config`
(`ConfigBuilder`, `ConfigHandler`, the four-layer read contract) composed with
the grammar this package declares. What the package owns is the grammar, the
layering policy, and the section→kwargs mapping.

## The recipe

`AsgiConfigBuilder` (builder.py:60) is the `asgiconfig` dialect: the contrib
`ConfigBuilder` composed with `AsgiServerGrammar` (builder.py:60,
`_name = "asgiconfig"` at :63). A site subclasses it and overrides
`main(self, root)`.

`BaseConfiguration` (builder.py:75) ships the package's own defaults **as a
recipe**, not as constructor fallbacks: `main` declares the `server` and
`storage` sections (builder.py:101-105), `server_section` declares the section
bare with no value at all (builder.py:107-115), and `storage_mounts` writes
`DEFAULT_SITE_MOUNT` as a recipe line anchored to the cwd **read when the
recipe runs** (builder.py:121-133). A site deviates by overriding one hook.

## The grammar

`AsgiServerGrammar` (elements.py:82) extends `TaskGrammar` — the task
capability declares its own words and they are composed in explicitly
(elements.py:82-90). The root `configuration` element overrides the contrib
root with the closed section list, every section a singleton `[0:1]`
(elements.py:91-104), so every path is stable and hand-writable.

| Section | Declared at | Becomes |
|---|---|---|
| `server` (+ `session`, `tasks`) | elements.py:107, :135 | `host`/`port`/`external_url`/`max_threads`, `session_ttl`, `tasks` |
| `middleware` | elements.py:141 | the `{name: bool \| dict}` switches |
| `authentication` (+ 6 children) | elements.py:164 | the identity stores AND the login surface |
| `storage` | elements.py:270 | genro-storage's mounts + `storage_key` |
| `applications` / `application` | elements.py:305, :311 | `applications`/`default` |
| `databases` / `database` | elements.py:332, :336 | one descriptor per handler |
| `plugins` / `plugin` | elements.py:350, :356 | the `plugins=` switches |
| `openapi` | elements.py:362 | nothing — declared, validated, no consumer |

**Grammar mounting works, and is the mechanism §2 of the README describes.** Two elements carry `_meta={"subbuilder": ...}`: `storage` mounts
`app:grammar` (elements.py:270) and `application` mounts `app_class:grammar`
(elements.py:311). From that node down the foreign grammar governs, while the
envelope's own attributes stay with this dialect. Proven by
`test_config.py:905` (an app's own subtree is read through the handler), `:919`
(the envelope attributes are the app's constructor kwargs) and `:929` (an
undeclared child of the mounted grammar raises).

**Validation is at recipe time, not at use time.** `test_config.py:320`
(unknown tag), `:328` (a section outside the root), `:336` (an application
without its class), `:354` (a mount without a base path, rejected by the
FOREIGN grammar), `:358` (storage without its app), `:377` (a second `server`
section), `:559` (a second `users` element), `:628`/`:638` (a provider without
a code, a duplicate code), `:683` (a stray child under `tasks`), `:873`/`:885`
(a group outside its collection, the pool at the top level).

**Secrets are refused as literals where it matters.** `admin_password` takes a
`BagResolver` as its node value and nothing else (elements.py:174-179);
`test_config.py:544` proves a literal is rejected at the recipe line, `:552`
that resolving empty is a boot error, and `test_config_env.py:236` that
resolving to a non-string is one too.

## The layers

`DefaultConfig` (default_config.py:64) resolves the three-layer chain.
`parents_for` (default_config.py:75) always puts `BaseConfiguration` lowest,
then the layer the recipe itself declares through `default_config`
(default_config.py:95, :80-94): unset/`None`/`True` takes the conventional
`<base_dir>/config.py` if it exists, `False` declines the layer, a path names
the file and **a missing one raises `ConfigError`** — an explicit choice the
runtime cannot honour is never a silent skip.

`base_dir` resolves explicit argument → `GENRO_ASGI_HOME` → `~/.genroasgi`
(default_config.py:67). The CLI's registry follows the same variable —
proven by `test_config.py:1151`.

The four `default_config` forms are proven by `test_config.py:1064` (unset),
`:1078` (`True`), `:1083` (`False` refuses even when the file is there), `:1091`
(an explicit path from anywhere), `:1101` (a missing explicit path is a
`ConfigError`). The layering itself: `test_config.py:1002` (a site inherits the
default mount and adds its key), `:1018` (the conventional recipe joins when
the file exists), `:1027` (the defaults layer beats the base and loses to the
site).

Layering is done on the tree with `Bag.update`, lowest first, and the datastore
is not merged — the contrib handler's contract, quoted at
`genro-builders/src/genro_builders/contrib/config/handler.py:13-17`.

## The read door

`ConfigurationHandler` (handler.py:68) subclasses the contrib `ConfigHandler`
and adds the section→kwargs helpers `AsgiServer.__init__` consumes. It **never
builds a server**: the server builds its own handler and asks for its kwargs.

The four-layer read stack is the contrib class's: written value (a resolver
there resolves at read time) → the grammar's annotated signature default,
resolved AT READ TIME → the call-site `default=` → a noisy `KeyError` carrying
the path. Proven by `test_config.py:944`, `:948`, `:957`, `:961`.

An application reads with paths relative to itself: `BaseApplication.config`
prefixes `applications.<code>.` and delegates
(`application.py:127-146`). `test_config_env.py:310` proves each application
reads only its own prefix; `:327`-`:341` prove an unconfigured or detached
application answers the call-site default and otherwise raises the same noisy
error.

Two reading rules, and the grammar decides which applies (handler.py:25-31): a
node with a CLOSED signature is read attribute by attribute through the handler
itself, so signature defaults and resolvers are honoured; a node with open
`**kwargs` is read in bulk through `builder.runtime_values`. The second is why
a database password given as a resolver still resolves —
`test_config_env.py:265`.

## What does NOT exist

**The tree is a read door only.** There is no writing and no notification, so
nothing in §5 of the README is implemented:

- `apply_configuration` has **zero occurrences** in `src/` and `tests/`;
- `config/handler.py` declares **no mutator** — searched for
  `set`/`write`/`update`/`apply`/`subscribe`/`on_change`, none found;
- no part of genro-asgi subscribes to the tree, and the administrative
  application carries no command that writes to it.

The machinery underneath does exist and is unused: the configuration tree is a
`SourceBag`, a `Bag` subclass (genro-builders
`src/genro_builders/builder/source_bag.py:636`), reachable as
`ConfigHandler.builder`; and `Bag.subscribe(subscriber_id, update=…, insert=…,
delete=…, any=…, transaction=…)` exists (genro-bag
`src/genro_bag/bag/_events.py:161`), with writes able to fire or suppress the
trigger (`set_item(..., do_trigger=…)`).

So what is absent is the writing door and the subscribers, not the mechanism
they would stand on.

**The live-config architecture is parked, not forgotten**: D23,
SPECIFICATION.md:418-419 — "the two-stage live-config architecture (config as
live object, `apply_configuration`, hot/cold changes) stays parked as a future
macro".

## Test inventory

Every test is a **contract test**; `tests/x/` holds only `__init__.py`.

| File | Items | Covers |
|---|---|---|
| `tests/test_config.py` | 81 | the self-configuring server, every section, grammar validation, the read stack, the layers, the declared defaults, home resolution |
| `tests/test_config_env.py` | 16 | resolvers end to end: server attributes, the storage key, secrets, open kwargs, application-side reads |

## Decisions that shaped what exists

- **Ratified 2026-07-29** (SPECIFICATION.md:772) — the config layer refounded
  on genro-builders `contrib/config`: the inherited four-layer read stack, an
  application reading its own prefix, and "explicitly passed kwargs win,
  wholesale per kwarg".
- **D15** (SPECIFICATION.md:171) — one config is the whole site; each process
  materializes its role's projection. The `Projection` object was later removed
  (the CLI ratification, SPECIFICATION.md:817, records that `--role`/`--app`
  lost their meaning with it).
- **D23** (SPECIFICATION.md:418-419) — the live-config architecture parked as a
  future macro.
- **The pool is not a section of this dialect** (elements.py:63-66): a pool
  belongs to the application that owns it, so its words live in that
  application's grammar under `applications.<code>.commander`. Proven by
  `test_config.py:885`.
