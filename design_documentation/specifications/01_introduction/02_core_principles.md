# Core Principles

Genro-ASGI follows four key principles:

1.  **Minimal Dependencies**: Only use essential packages (`uvicorn`, `pyyaml`, `genro-toolbox`, `genro-routes`, `genro-tytx`).
2.  **No Magic**: Configuration is explicit and behavior must be predictable.
3.  **Composable**: Built as a set of components (Middleware, App, Router) that can be combined or replaced.
4.  **Type-safe**: Extensive use of type hints for better maintainability and integration with `genro-tytx`.
