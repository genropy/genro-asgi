# Applications

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The need.** Behaviour must be mountable: an application owns its routes and
its identity, and the server hosts many without knowing their insides.

`RoutedApplication` and its route tree — one tree, several interchangeable
faces: [openapi](openapi/) (REST + OpenAPI 3.1 + Swagger) and [mcp](mcp/)
(the router as MCP tools). An application declares its own recipe words
through its `ApplicationGrammar`.

Interactions: server (mounts by `code`, demux D3) · plugins (dialects arrive as plugins) · every concrete app.
