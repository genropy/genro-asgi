# Monitor — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## Application contributions and admin gate

`MonitorSection` supplies the monitor page and snapshot through the
`SERVER_ADMIN`-guarded core surface. It asks each application for
`app_snapshot` and `app_panel`; an optional `panel_source` provides its client
panel code. `BaseApplication` supplies a generic snapshot and panel fallback.
The section uses this contribution contract rather than importing SPA classes.

The current application/worker projections are what these contributors return.
Historical monitor/workbench branches, full pre-refactoring panel parity and
Prometheus export are not established by this implementation. The local MkDocs
internals reader is a separate developer documentation tool.

Claim anchors: [`MonitorSection`](../../../../src/genro_asgi_server_app/server_sections/monitor_section.py#L75), [`app_snapshot`](../../../../src/genro_asgi/application.py#L170), [`app_panel`](../../../../src/genro_asgi/application.py#L180), [`BaseApplication`](../../../../src/genro_asgi/application.py#L86).

## Source and test evidence

- [src/genro_asgi_server_app/server_sections/monitor_section.py](../../../../src/genro_asgi_server_app/server_sections/monitor_section.py)
- [src/genro_asgi/application.py](../../../../src/genro_asgi/application.py)
- [src/genro_asgi_multiworker_spa/spa_app.py](../../../../src/genro_asgi_multiworker_spa/spa_app.py)
- [tests/server_app/test_server_monitor.py](../../../../tests/server_app/test_server_monitor.py)
