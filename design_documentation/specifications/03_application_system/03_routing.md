# Routing with genro-routes

Genro-ASGI uses `genro-routes` to map URLs to Python methods. This provides a clean, declarative way to define endpoints.

## The @route Decorator
Each handler method is decorated with `@route`. You can specify:
- **Path**: Explicit URL or inferred from method name.
- **Auth Tags**: Required permissions (e.g., `auth_tags="admin"`).
- **Env Capabilities**: Environment requirements (e.g., `has_jwt`).
- **MIME Type**: Expected output format (e.g., `text/html`).

## Hierarchical Routing
Since applications are mounted at specific paths (e.g., `/shop`), the routing system automatically prefixes the application's routes. A route `/products` inside a `ShopApp` mounted at `/shop` becomes accessible at `/shop/products`.
