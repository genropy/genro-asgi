# CLI — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 evidence refreshed; design ratification unchanged

Verified against source revision `2465fcc` (develop baseline). Test references
below identify the executable contracts; they are not a new coverage percentage.

## Commands and instance records

The `genro-asgi` entry point is `genro_asgi.__main__:main`. It provides `serve`,
`apps`, `stop` and `remove`. `serve` loads the same recipe as Python server
construction; named instances record their location and process state under
the configured Genro ASGI home and wire a session snapshot. `apps` reads that
registry; `stop` signals the recorded process; `remove` removes its registry
entry according to the command's checks.

`serve --reload` runs through `reloading.factory`, which marks the child
shutdown mode `QUITTING` so SPA shutdown preserves restart state. `--debug`
declares a usage mode and is not the reload mechanism. The default listener
and explicit/configured address precedence are shared with `AsgiServer`.

These commands do not implement the proposed general administrative restart
liturgy or a deployment/subcommander controller.

Claim anchors: [`apps`](../../../src/genro_asgi/__main__.py#L459), [`remove`](../../../src/genro_asgi/__main__.py#L127), [`remove`](../../../src/genro_asgi/__main__.py#L489), [`factory`](../../../src/genro_asgi/__main__.py#L498), [`AsgiServer`](../../../src/genro_asgi/asgi_server.py#L91).

Behavior evidence: [`ServerLauncher`](../../../src/genro_asgi/__main__.py#L212), [`AppsRegistry`](../../../src/genro_asgi/__main__.py#L88), [`TargetResolver`](../../../src/genro_asgi/__main__.py#L163).

## Source and test evidence

- [src/genro_asgi/__main__.py](../../../src/genro_asgi/__main__.py)
- [src/genro_asgi/reloading.py](../../../src/genro_asgi/reloading.py)
- [src/genro_asgi/asgi_server.py](../../../src/genro_asgi/asgi_server.py)
- [tests/core/test_cli.py](../../../tests/core/test_cli.py)
- [tests/core/test_reloading.py](../../../tests/core/test_reloading.py)
