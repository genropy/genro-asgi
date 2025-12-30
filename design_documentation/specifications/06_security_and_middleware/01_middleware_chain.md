# Middleware Pipeline

Genro-ASGI uses a layered middleware architecture to handle cross-cutting concerns.

## The Chain of Responsibility
Middleware components are executed in a specific order defined in the configuration. Each component can inspect the request, modify it, or return a response early.

## Core Middleware
- **ErrorMiddleware**: Catches exceptions and returns clean HTTP error responses. Usually high priority (executed first).
- **AuthMiddleware**: Extracts authentication data (JWT) and populates the `scope['auth_tags']`.
- **CorsMiddleware**: Handles Cross-Origin Resource Sharing headers for web browser compatibility.
- **LoggingMiddleware**: Records request and response metadata for debugging and auditing.
