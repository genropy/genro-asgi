# Genro-ASGI Functional Table of Contents

This document presents a progressive and functional vision of `genro-asgi`, structured to guide a user from basic concepts to advanced architectures.

## 1. Introduction and Vision
*   **Project Vision**: Minimalism, Composability, and Type-safety.
*   **Core Principles**: "No Magic", Explicitness, and Consistency.
*   **Glossary and Terminology**: Server, App, Router, Middleware, Handler, Endpoint.
*   **Quick Start**: Installation and creating the first minimal application.

## 2. Server Foundation (The Orchestrator)
*   **AsgiServer**: The core of the system and its coordination responsibilities.
*   **Dynamic Configuration**: Management via YAML, environment variables, and CLI.
*   **Lifecycle Management**: Handling Startup and Shutdown signals (Lifespan).
*   **Multi-App Mounting**: How to isolate and mount multiple applications on the same server.

## 3. Anatomy of an Application (AsgiApplication)
*   **The AsgiApplication Model**: Base structure and lifecycle hooks (`on_init`, `on_startup`, `on_shutdown`).
*   **Functional Routing**: Using the `@route` decorator and integration with `genro-routes`.
*   **Application Context**: Accessing parent server resources and path isolation.

## 4. Request and Response Management
*   **Request System**: `HttpRequest` and `MsgRequest` (Typed abstractions).
*   **Response System**: Automatic response generation (JSON, HTML, File) and `set_result`.
*   **Context Injection**: Automatic handling of `auth_tags` and `env_capabilities` in requests.
*   **Static Assets**: Serving static files via `StaticRouter`.

## 5. Data, State, and Resources
*   **Resource Loader**: Hierarchical resource loading with fallback logic.
*   **LocalStorage**: Asynchronous and non-blocking file system (`smartasync`).
*   **State Management**: Persistence concepts and session management (Stateless vs. Stateful).

## 6. Security and Pipeline (Middleware)
*   **The Middleware Chain**: Layered architecture and execution priority.
*   **Authentication**: JWT management and `AuthMiddleware` integration.
*   **Granular Authorization**: RBAC based on route tags.
*   **Cross-Cutting Concerns**: CORS management, Error Logging, and Exception Handling.

## 7. Specialized Application Models
*   **StaticSite**: Applications for static content distribution only.
*   **ApiApplication**: Data-oriented and JSON-first services.
*   **PageApplication**: Rendering HTML views and template engine integration.
*   **System Apps**: 
    *   `SwaggerApp`: Automatic OpenAPI documentation.
    *   `GenroApiApp`: Interactive endpoint exploration.

## 8. Real-time and Advanced Protocols
*   **Native WebSocket**: Permanent bidirectional connection management.
*   **WSX Protocol (Extended WebSockets)**: Transparent and typed RPC between Python and Javascript.

## 9. Process Architectures and Scalability
*   **Orchestrator/Worker Separation**: Strategies to isolate the server from heavy application logic.
*   **Deployment Topologies**: Local execution vs. distributed infrastructures.
*   **Executor System**: Managing thread and process pools for CPU-intensive tasks.

## 10. Advanced SPA Management (SpaManager)
*   **Interaction Hierarchy**: User → Connection → Session → Page.
*   **Stateful Workers**: Session affinity management for complex SPAs.
*   **Single Page Application Lifecycle**: Tracking and managing active pages and their resources.
*   **Future Developments**: NATS integration, Blue-Green deployment, and state migration.
