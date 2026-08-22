# Plugins

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The need.** The core must be extendable without being forked: capabilities arrive as plugins, plugged by name.

`PluginMixin` (composed BEFORE the server class) merges a `{name: class}`
registry over `default_plugin_registry()`; each plugin class is registered
with genro-routes (idempotent). Transport-dialect plugins in this package
carry a class; native plugins (auth/channel/env/logging/pydantic) are
plugged by name without one.

Interactions: applications (the dialects) · server-application (the future `plugin_config` page administers this tree).
