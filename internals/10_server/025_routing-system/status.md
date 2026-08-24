# Routing system — current state

**Version**: 0.4 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

What exists TODAY on `develop`. Every claim below carries its `file:line` or
the test that proves it. Coverage figures are from the full suite
(`pytest tests/`, 1463 passed) run on 2026-08-23 at `9660561`.

## Where the routing system lives

**Almost none of it is in this package.** The tree, the walk, the three filter
plugins and the plugin base class are genro-routes'
(`genro-routes/src/genro_routes/`): `core/routing.py` carries `RoutingClass` and
the `route` marker, `core/base_router.py` the tree and `add_branches`,
`core/router.py` the process-wide plugin registry, and `plugins/` the five
bundled plugins — `auth`, `env`, `channel`, `pydantic`, `logging`.

What this package owns is the arming (`plugin_mixin.py`), the one dialect plugin
it ships, and the configuration section. So the modules below are the seam, not
the subject; the pin is `genro-routes>=0.28` in `pyproject.toml`.

**The three filters, in the library:** `plugins/auth.py` (tags),
`plugins/env.py` (capabilities, with `CapabilitiesSet` and the accumulation
down the tree), `plugins/channel.py` (channels, matched as patterns so
`bot_.*` works).

**All three have a live consumer in this core, and only one of them is the HTTP
dispatch's.** Tags are passed by
[routed_application.py:197-208](../../../src/genro_asgi/routed_application.py),
which is the path every HTTP request takes. The other two are read by the two
faces:

| Filter | Read by | Where |
|---|---|---|
| tags | the HTTP dispatch, and the MCP engine on both its calls | `routed_application.py:178`, [mcp/engine.py:291](../../../src/genro_asgi/mcp/engine.py) |
| channel | **the MCP engine**, on the tool list and on every tool call | `mcp/engine.py:205`, `:292` |
| capabilities | the OpenAPI translator, published as `x-requires` | [translator.py:245-247](../../../src/genro_asgi/plugins/openapi/translator.py) |

The middle row is the design's claim made concrete: the MCP face walks the same
tree with `channel_channel` set to its own channel, so a route marked for one
surface does not appear on the other. The HTTP dispatch passes no channel at
all, which is why every route is reachable over HTTP unless its tags say
otherwise.

## The modules

| Module | Lines | Stmts | Miss | Cov | Uncovered |
|---|---|---|---|---|---|
| `src/genro_asgi/plugin_mixin.py` | 148 | 46 | 0 | 100% | — |
| `src/genro_asgi/plugins/__init__.py` | 28 | 3 | 0 | 100% | — |
| `src/genro_asgi/plugins/openapi/__init__.py` | 74 | 14 | 2 | 86% | 72-73 |
| `src/genro_asgi/plugins/openapi/plugin.py` | 93 | 26 | 6 | 77% | 81, 83, 85, 87, 89, 91 |

`plugins/openapi/translator.py` (307 lines, 86%) sits in this package and is
**not this entry's subject**: it turns the neutral description into an OpenAPI
document and belongs to
[020 applications / openapi](../020_applications/openapi/). Same for
`router_openapi` (`plugins/openapi/__init__.py:39`), whose single caller is
[openapi.py:141](../../../src/genro_asgi/applications/openapi.py).

## `PluginMixin` — [plugin_mixin.py:74](../../../src/genro_asgi/plugin_mixin.py)

**Composition.** Peels `plugins` and `plugin_registry` in `__init__`
(plugin_mixin.py:87-88), runs the chain, then merges the extras over
`default_plugin_registry()` (plugin_mixin.py:90-93) and resolves the switches
(`:94`). Composed before `BaseServer` in `AsgiServer`
([asgi_server.py:91-100](../../../src/genro_asgi/asgi_server.py)).

**The fixed pair.** `FIXED_PLUGINS = ("pydantic", "openapi")`
(plugin_mixin.py:61). `_resolve_plugins` (plugin_mixin.py:96-118) seeds the
result with both (`:108`) and raises `ValueError` when a falsy value names one
of them (`:110-111`); a dict value becomes the plug options (`:112-113`), a
truthy scalar enables an extra with none (`:114-115`), a falsy value drops an
extra (`:116-117`). Proven by `test_plugins.py:137`
(`test_disabling_a_fixed_plugin_is_a_config_error`), `:115` (a dict tunes the
fixed plugin), `:141` (an extra is retained beside the base), `:154` (`False`
leaves an extra unarmed), `:243` (no `plugins` config still arms the base).

**The registry is a call, not a module global.** `default_plugin_registry()`
(plugin_mixin.py:64-71) returns a **fresh** `{"openapi": OpenAPIPlugin}` per
call. Proven by `test_plugins.py:92`, `:95`
(`test_default_registry_is_fresh_each_call`), `:100` (extension merges over the
default).

**No import side effect.** Importing the package registers nothing against the
routing library; proven by `test_plugins.py:221`
(`test_importing_the_package_does_not_register_openapi`).

**Arming.** `arm_router(router)` (plugin_mixin.py:130-148) reads the codes
already on the tree (`:139`), registers a class the routing library does not
know yet (`:143-144`), collects the not-yet-attached codes and plugs them in a
single batch call (`:145-148`). Proven by `test_plugins.py:109` (arms an
enabled plugin), `:123` (a bundled plugin plugs by name alone), `:129` (a
registry extension arms a custom class), `:147` (arming registers it in the
routing library's registry), `:164` (`test_arming_twice_is_a_no_op`), `:172`
(an unknown code raises).

**Who calls it, and when.** One caller: the `route` property of
`RoutedApplication`
([routed_application.py:143-156](../../../src/genro_asgi/routed_application.py)),
on the first access made once a server owns the application. Proven by
`test_plugins.py:233` (an unmounted app arms nothing extra) and `:237` (a
mounted app arms on first access). A composition without this mixin exposes no
`arm_router`, and the application keeps only what it armed itself.

**The third always-present plugin is not this mixin's.** `auth` is plugged by
the application on its own tree in its constructor
(routed_application.py:124), so it is there before any server sees the
application.

**Nothing is armed until the tree is first read.** Driven live on the recipe at
the foot of [README.md](README.md): with the server fully constructed and
`_armed` still `False`, the tree answers `['auth']`; after the first access to
`route` it answers `['auth', 'logging', 'openapi', 'pydantic']`. Reading the
tree without triggering the arming takes `RoutingClass.route.fget(app)`, which
is how the first figure was obtained.

## The configuration section

`plugins` / `plugin` are declared at
[elements.py:350](../../../src/genro_asgi/config/elements.py) and `:356`:
a collection keyed by `code`, each entry carrying `enabled` (default `True`)
and arbitrary options. `ConfigurationHandler.plugins_config`
([handler.py:234-253](../../../src/genro_asgi/config/handler.py)) turns them
into the `{code: bool | dict}` switches — `False` when `enabled` is explicitly
false, the remaining options when there are any, else `True` — and returns
`None` when the section is absent. `AsgiServer._configured_kwargs` maps it to
the `plugins` kwarg (asgi_server.py:160-166). Proven by `test_plugins.py:197`,
`:201`, `:206`.

**`plugin_registry` has no configuration counterpart.** It is named in
`AsgiServer`'s own docstring (asgi_server.py:41) and peeled by the mixin, and
`_configured_kwargs` never produces it — searched across `src/`, the only
occurrences are those two. So a plugin class a site brings can reach a server
only through Python construction. See [design.md](design.md), friction S3.

## `OpenAPIPlugin` — [plugin.py:49](../../../src/genro_asgi/plugins/openapi/plugin.py)

The one dialect plugin this package ships. `plugin_code = "openapi"`
(plugin.py:57); `configure` (plugin.py:60-71) declares eight accepted keys and stores nothing
itself — the routing library's base class does. Seven of the eight are the
plugin's own; the eighth, `enabled`, is the base class's and is handled there
(`genro-routes/src/genro_routes/plugins/_base_plugin.py:371`).

**`entry_metadata` (plugin.py:73-93) contributes a block nobody reads.** It
repackages the seven options and the routing library files the result at
`entry["plugins"]["openapi"]["metadata"]`
(`genro-routes/src/genro_routes/core/router.py:600`). The OpenAPI reader takes
its values from a different key of the same description —
`entry["metadata"]["plugin_config"]["openapi"]`, the raw configuration
(translator.py:164) — and never looks at the contributed block. Searched: the
translator reads `entry["plugins"]` only for `auth` and `env`
(translator.py:226-242).

**Six of its seven contributions are also untested**, which follows from having
no consumer. Only the method override (plugin.py:79) is exercised, by
`test_plugins.py:329` (`test_method_override_from_handler_config`). Uncovered:
`tags` (`:81`), `summary` (`:83`), `description` (`:85`), `deprecated` (`:87`),
`security_scheme` (`:89`) and the explicit `security` override (`:91`). See
[design.md](design.md), friction S4.

**Per-route configuration is written `<code>_<key>` at the route.** The
fixture at `test_plugins.py:80` uses `@route(openapi_method="delete")`. Driven
live on the recipe at the foot of [README.md](README.md):
`@route(openapi_method="delete", openapi_tags="admin")` publishes `/drop` as a
`DELETE` carrying `tags: ['admin']`, while the route beside it keeps the
guessed `GET`.

**`plugins/openapi/__init__.py:72-73` is uncovered**: the `basepath` branch of
`router_openapi`, which rewrites paths as absolute. It belongs to
[020 applications / openapi](../020_applications/openapi/).

## The registration is process-wide, and the first class wins

`Router.register_plugin` writes into a **class-level** registry of the routing
library (`genro-routes/src/genro_routes/core/router.py:116`), read back by
`Router.available_plugins()` (`:145`). `arm_router` guards on that registry
(plugin_mixin.py:143), so a code already registered is never re-registered —
by any server.

Driven live: two servers built in one process, each with its own
`plugin_registry` mapping the code `mine` to a different class, and each arming
its own application. The first server's class is registered; **the second
server's tree carries the first server's class**, and nothing is raised or
logged. See [design.md](design.md), friction S2.

At import the routing library makes five codes available — `auth`, `channel`,
`env`, `logging`, `pydantic` — and `openapi` joins them the first time any
server arms a tree.

## Test inventory

Every test is a **contract test**; `tests/x/` holds only `__init__.py`.

| File | Items | Covers |
|---|---|---|
| `tests/test_plugins.py` | 32 | the registry, arming, the config-driven path, no import side effect, lazy arming — and the OpenAPI translator |

Of the 32, eleven belong to
[020 applications / openapi](../020_applications/openapi/): the classes
`TestTranslator` (`test_plugins.py:255`) and `TestRouterOpenapi` (`:311`)
exercise the dialect, not the plug mechanism. This entry's own are the
twenty-one in `TestDefaultRegistry`, `TestArmRouter`, `TestConfigDriven`,
`TestNoImportSideEffect` and `TestLazyArming`.

## Decisions that shaped what exists

- **D17** (SPECIFICATION.md:229) — capabilities are mixins, amending D2's
  closed list. `PluginMixin` is one.
- **D16** (SPECIFICATION.md:217) — cooperative init. Held: `plugins` and
  `plugin_registry` are peeled here and the rest forwarded.
- **D26** (SPECIFICATION.md:456) — `pydantic` and `openapi` are fixed server
  structure, so per-entry OpenAPI controls always apply. Implemented as
  `FIXED_PLUGINS` and enforced with a `ValueError`.
- **D22 scope ruling** (SPECIFICATION.md:363) — the complete OpenAPI and MCP
  applications belong to the core. The dialect plugin living here rather than
  in the routing library follows from it.
- The no-import-side-effect and no-module-level-registry rules are the coding
  rules', recorded in the modules' own contracts
  (plugin_mixin.py:35-38, plugins/openapi/plugin.py:35-37); no D-entry states
  them.

## Two facts a reader of the design should be able to check

**A published verb does not gate the dispatch.** `RoutedApplication.__call__`
never reads `scope["method"]`, so the verb an entry declares is carried into
the schema and nowhere else. Driven live on the recipe at the foot of
[README.md](README.md): `POST /search` answers **200** although the route is
published as a `GET`. See [design.md](design.md), friction S7.

**A plugin of one's own does work, end to end.** Driven live: a `BasePlugin`
subclass with `plugin_code = "owner"`, a `configure` declaring `team`/`oncall`
and an `entry_metadata` returning a block, handed to a server as
`plugin_registry={"owner": OwnerPlugin}` and named in the description as
`plugins().plugin(code="owner")`. The tree then carries
`['auth', 'openapi', 'owner', 'pydantic']` and the entry's description holds
`plugins.owner.config = {'enabled': True, 'team': 'retail'}` and
`plugins.owner.metadata = {'owner': {'team': 'retail', 'oncall': ''}}`. The
five hooks a plugin may implement — `configure`, `on_decore`, `wrap_handler`,
`deny_reason`, `entry_metadata` — are the routing library's
(`genro-routes/src/genro_routes/plugins/_base_plugin.py:26-33`), and nothing in
this package narrows them.
