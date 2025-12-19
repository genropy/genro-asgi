# 09 - Authentication & Context System

**Version**: 0.1.0
**Last Updated**: 2025-12-19
**Status**: Draft - Design Decisions

This document captures the architectural decisions for authentication and context management in genro-asgi.

## Overview

genro-asgi provides a minimal, API-first authentication system based on JWT tokens. The design follows clear separation of concerns between routing, authentication, and authorization.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     REQUEST FLOW                             │
├─────────────────────────────────────────────────────────────┤
│  HTTP Request                                                │
│       ↓                                                      │
│  JWTAuthMiddleware → extracts token, populates avatar       │
│       ↓                                                      │
│  Dispatcher creates AsgiContext(request, app, server)       │
│       ↓                                                      │
│  Router.dispatch() → AuthPlugin checks auth_tags            │
│       ↓                                                      │
│  Match? → Handler / No match? → NotAuthorized               │
│       ↓                                                      │
│  Dispatcher catches NotAuthorized → 401/403 JSON            │
└─────────────────────────────────────────────────────────────┘
```

## Key Decisions

### Decision 1: API-First Design

**Decision**: genro-asgi always returns JSON responses for auth errors, never redirects.

**Rationale**:
- Modern SPA pattern: frontend handles 401/403 and decides UX
- Server stays stateless and simple
- Same behavior for API clients and SPA

**Consequence**:
- 401 → `{"error": "authentication_required"}`
- 403 → `{"error": "forbidden"}`
- No `login_url` configuration in server
- Redirect to login is frontend responsibility

### Decision 2: JWT as Primary Token Format

**Decision**: Use JWT (JSON Web Tokens) for API authentication.

**Rationale**:
- Stateless: no server-side session storage needed
- Self-contained: carries user_id and tags
- Standard: widely supported, well-understood
- No Redis or session store required

**Configuration**:
```yaml
middleware:
  - jwt_auth:
      secret: "${JWT_SECRET}"
      algorithms: ["HS256"]
```

**Token structure**:
```json
{
  "sub": "user_id",
  "tags": ["user", "admin"],
  "exp": 1234567890
}
```

### Decision 3: Hybrid Cookie + Bearer Support

**Decision**: Middleware accepts both `Authorization: Bearer` header and session cookie.

**Rationale**:
- API clients use Bearer token
- SPA can use httponly cookie (more secure for browser)
- Same middleware handles both

**Priority order**:
1. `Authorization: Bearer <token>` (API clients)
2. `Cookie: session=<token>` (SPA/browser)

### Decision 4: Separation of Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **JWTAuthMiddleware** | Decode token → populate `avatar` in scope |
| **AuthPlugin (genro-routes)** | Check `auth_tags` vs `avatar.tags` → `NotAuthorized` |
| **Dispatcher** | Catch `NotAuthorized` → determine 401 vs 403 |
| **App/Frontend** | Decide what to do with 401 (redirect, modal, etc.) |

**Key principle**: genro-routes knows nothing about HTTP. It only raises `NotAuthorized`. genro-asgi translates this to HTTP status codes.

### Decision 5: 401 vs 403 Logic

**Decision**: Dispatcher determines status code based on avatar presence.

```python
except NotAuthorized:
    if context.avatar is None:
        # Not authenticated → 401
        return JSONResponse({"error": "authentication_required"}, status=401)
    else:
        # Authenticated but insufficient permissions → 403
        return JSONResponse({"error": "forbidden"}, status=403)
```

| Scenario | avatar | Status | Response |
|----------|--------|--------|----------|
| No token | None | 401 | `{"error": "authentication_required"}` |
| Invalid token | None | 401 | `{"error": "authentication_required"}` |
| Valid token, wrong tags | present | 403 | `{"error": "forbidden"}` |
| Valid token, correct tags | present | 200 | Handler response |

### Decision 6: AsgiContext as RoutingContext Implementation

**Decision**: `AsgiContext` implements `RoutingContext` from genro-routes.

```python
class AsgiContext(RoutingContext):
    """ASGI-specific execution context."""

    @property
    def avatar(self) -> Any:
        """User identity from auth middleware."""

    @property
    def session(self) -> Any:
        """Session data (if middleware configured)."""

    @property
    def db(self) -> Any:
        """Database connection from app/request."""

    @property
    def app(self) -> AsgiApplication:
        """Application instance."""

    @property
    def server(self) -> AsgiServer:
        """Server instance."""
```

**Extensibility**: Future projects (like genropy-server) can create `GenropyContext(AsgiContext)` with additional properties like `page`, `connection`, `user` stores.

### Decision 7: Route-Level Authorization via Metadata

**Decision**: Use `@route` decorator `meta_` parameters for auth requirements.

```python
@route("api")  # Public - no auth required
def health(self):
    return {"status": "ok"}

@route("api", meta_auth_tags=["user"])  # Requires "user" tag
def get_my_orders(self):
    ...

@route("api", meta_auth_tags=["admin"])  # Requires "admin" tag
def delete_user(self, user_id):
    ...
```

**Rationale**:
- Declarative: auth requirements visible in code
- Handler stays transport-agnostic
- AuthPlugin reads metadata and enforces

### Decision 8: No Built-in Login Endpoint

**Decision**: genro-asgi does not provide built-in login/token endpoints.

**Rationale**:
- Login logic varies (password, OAuth, passkey, etc.)
- Token generation is application-specific
- Keep framework minimal

**Application provides**:
```python
@route("auth")
def login(self, username: str, password: str):
    avatar = self.app.get_avatar(username, password)
    if not avatar:
        raise NotAuthorized()
    token = self._create_jwt(avatar)
    return {"access_token": token}
```

## Future Considerations

### genropy-server Extension

For Genropy applications, a separate package will provide:
- `GenropyContext` with `page`, `connection`, `user` stores
- Daemon with user/connection/page registries
- Hierarchical store pattern

```
RoutingContext (genro-routes)
       │
       └── AsgiContext (genro-asgi)
                 │
                 └── GenropyContext (genropy-server)
```

### Additional Auth Methods

The middleware pattern allows adding:
- API Key authentication
- OAuth2/OIDC integration
- Passkey/WebAuthn support

Each would be a separate middleware that populates `avatar`.

## Configuration Example

```yaml
# config.yaml
middleware:
  - jwt_auth:
      secret: "${JWT_SECRET}"
      algorithms: ["HS256"]
      cookie_name: "session"  # Optional: also check this cookie

plugins:
  - auth:
      tags_key: "auth_tags"  # meta_ key for route auth requirements
```

## Summary

| Aspect | Decision |
|--------|----------|
| Token format | JWT (HS256) |
| Token location | Bearer header + optional cookie |
| Auth errors | Always JSON (401/403) |
| Redirect to login | Frontend responsibility |
| Route protection | `meta_auth_tags` in `@route` |
| Session storage | Not required (stateless JWT) |
| Login endpoint | Application provides |
