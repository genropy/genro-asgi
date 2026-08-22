# Configuration

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The need.** An admin describes an installation ONCE — which apps, which pools, which doors — and starts it by name. The recipe, not code, is where one installation differs from another.

The recipe that builds a server: the config builder and its grammar, the
layered `config.py` under `GENRO_ASGI_HOME`, environment variables, and the
`genroasgi` CLI (`serve` / `apps` / `stop` / `remove`, `--reload`, named
instances). Every other feature reads its own subtree of the recipe; an
application adds its own words through its `ApplicationGrammar` (the SPA
front declares its pool and groups under `applications.<code>.commander`).

Interactions: every feature (each reads its recipe subtree) · spa-application (grammar).
