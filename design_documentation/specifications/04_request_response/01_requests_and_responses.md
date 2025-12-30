# Request and Response System

Genro-ASGI provides high-level abstractions for handling HTTP and Message-based traffic.

## Request Types
- **HttpRequest**: A wrapper for standard HTTP calls, providing easy access to headers, query parameters, and JSON bodies.
- **MsgRequest**: Used for WebSocket messages and internal RPC calls.

## Response Abstraction
The `Response` system simplifies sending data back to the client:
- **set_result(data)**: Automatically detects the best format (JSON, HTML, or String).
- **FileResponse**: For efficient streaming of static assets or generated files.
- **Redirects**: Simple utilities for path redirection.

## Context Injection
Every request automatically carries security context (`auth_tags` and `env_capabilities`), which is injected during the routing phase, allowing handlers to make immediate authorization decisions.
