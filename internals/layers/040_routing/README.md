# Routing and API surfaces

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

**The shelf.** The route tree and its interchangeable API faces (REST/OpenAPI, MCP).

`RoutedApplication` and its route tree, exposed through interchangeable
faces: `OpenApiApplication` (REST + OpenAPI 3.1 + Swagger page) and
`McpApplication` / `McpOpenApiApplication` (MCP tools over stateless
Streamable HTTP). One tree, several dialects.

Interactions: console (MCP face) · server-application · every routed app.
