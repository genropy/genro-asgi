# Routing with genro-routes

Genro-ASGI uses `genro-routes` to map methods to routes. The final URL path is determined by the mount hierarchy, not by the decorator.

## The @route Decorator

Each handler method is decorated with `@route`. You can specify:

- **Router name**: Which router to register the method in (optional if only one router exists).
- **Auth Tags**: Required permissions (e.g., `auth_tags="admin"`).
- **Env Capabilities**: Environment requirements (e.g., `has_jwt`).
- **MIME Type**: Expected output format (e.g., `meta_mime_type="text/html"`).

The **path segment** is derived from the **method name** (e.g., `def hello()` → `hello`).

## Hierarchical Routing

The final URL is built from the mount hierarchy:

- App mounted at `/shop` with method `products` → `/shop/products`
- App mounted at `/api/v1` with method `users` → `/api/v1/users`

The developer never specifies explicit URL paths in decorators.
