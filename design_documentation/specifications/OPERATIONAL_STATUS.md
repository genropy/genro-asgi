# Genro-ASGI Operational Status

This document maps the functional structure of the project to the actual implementation status.

## 1. Core Framework (src/genro_asgi)

| Feature | Status | File/Reference | Notes |
|---------|--------|----------------|-------|
| **AsgiServer** | ✅ Ready | `server.py` | Main entry point, uvicorn integration. |
| **Server Config** | ✅ Ready | `server_config.py` | YAML and CLI support. |
| **AsgiApplication** | ✅ Ready | `application.py` | Base class with hooks. |
| **Dispatcher** | ✅ Ready | `dispatcher.py` | Routing via `genro-routes`. |
| **Lifespan** | ✅ Ready | `lifespan.py` | Full startup/shutdown protocol. |
| **Request System** | ✅ Ready | `request.py` | `HttpRequest` and `MsgRequest`. |
| **Response System** | ✅ Ready | `response.py` | Multi-format via `set_result`. |
| **WebSocket** | ✅ Ready | `websocket.py` | Persistent connection management. |
| **WSX Protocol** | ✅ Ready | `wsx/` | RPC protocol for WebSockets. |

## 2. Middleware & Safety

| Feature | Status | File/Reference | Notes |
|---------|--------|----------------|-------|
| **AuthMiddleware** | ✅ Ready | `middleware/authentication.py` | JWT and auth_tags support. |
| **CorsMiddleware** | ✅ Ready | `middleware/cors.py` | YAML configuration. |
| **ErrorMiddleware** | ✅ Ready | `middleware/errors.py` | Exception handling. |

## 3. Storage & Resources

| Feature | Status | File/Reference | Notes |
|---------|--------|----------------|-------|
| **LocalStorage** | ✅ Ready | `storage.py` | Async file system. |
| **ResourceLoader** | ✅ Ready | `resources.py` | Hierarchical fallback. |

## 4. Roadmap & Design

| Feature | Status | Notes |
|---------|--------|-------|
| **Session System** | ❌ Missing | Required for non-JWT state. |
| **SpaManager** | 📋 Designed | Strategic core for stateful workers. |

---
**Last operational update**: 2025-12-30
