# Server application (`_server`) — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## Automatic system application

`AsgiServer._register_server_app` mounts `ServerApplication` when no application
with code `_server` is already present. `BaseServer` alone does not add it.
`ServerApplication` extends `OpenApiApplication` and attaches auth, users,
tokens, tasks and monitor sections. Its public descriptor lists attached names.
Password and configured OIDC methods are registered under the auth section.

The monitor declares `SERVER_ADMIN`; users, tokens and tasks declare
`SUPERADMIN`. The login surface is public. `_request` injection comes from the common
`RoutedApplication.bind_kwargs`, not a private server-app override.

Claim anchors: [`AsgiServer`](../../../src/genro_asgi/asgi_server.py#L91), [`_register_server_app`](../../../src/genro_asgi/asgi_server.py#L205), [`ServerApplication`](../../../src/genro_asgi/applications/server_app.py#L111), [`RoutedApplication`](../../../src/genro_asgi/routed_application.py#L111), [`bind_kwargs`](../../../src/genro_asgi/routed_application.py#L272).

Behavior evidence: [`MonitorSection`](../../../src/genro_asgi/applications/server_sections/monitor_section.py#L75), [`UsersSection`](../../../src/genro_asgi/applications/server_sections/users_section.py#L61), [`TokensSection`](../../../src/genro_asgi/applications/server_sections/tokens_section.py#L57), [`TasksSection`](../../../src/genro_asgi/applications/server_sections/tasks_section.py#L60).

## SPA inspector and unfinished administration

The inspector is not imported by the core server application. A SPA front
attaches its own inspector at startup when `GNR_ASGI_INSPECTOR` is present.
That diagnostic surface has no route auth rule; its mounting gate differs from
the monitor's `SERVER_ADMIN` protection.

Per-section configurable tags, a plugin configuration page, general dynamic
application installation and monitor/workbench proposals are not delivered by
the current section list.

Behavior evidence: [`on_startup`](../../../src/genro_asgi_multiworker_spa/spa_app.py#L631), [`InspectorSection`](../../../src/genro_asgi_multiworker_spa/inspector_section.py#L61).

## Source and test evidence

- [src/genro_asgi/asgi_server.py](../../../src/genro_asgi/asgi_server.py)
- [src/genro_asgi/applications/server_app.py](../../../src/genro_asgi/applications/server_app.py)
- [src/genro_asgi/routed_application.py](../../../src/genro_asgi/routed_application.py)
- [src/genro_asgi_multiworker_spa/spa_app.py](../../../src/genro_asgi_multiworker_spa/spa_app.py)
- [src/genro_asgi_multiworker_spa/inspector_section.py](../../../src/genro_asgi_multiworker_spa/inspector_section.py)
- [tests/core/test_server_application.py](../../../tests/core/test_server_application.py)
- [tests/core/test_server_monitor.py](../../../tests/core/test_server_monitor.py)
- [tests/spa/test_inspector_section.py](../../../tests/spa/test_inspector_section.py)
