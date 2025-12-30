# Terminology and Glossary

To ensure consistency across the framework and its documentation, we use the following terms with specific meanings:

## Core Components

| Term | Description |
|------|-------------|
| **Server** (`AsgiServer`) | The ASGI entry point. It manages the server's lifecycle, configuration, and app orchestration. |
| **Application** (`AsgiApplication`) | A logical unit mounted on the server that handles a specific set of functionalities. |
| **Dispatcher** | The component responsible for routing incoming requests to the correct application handlers. |
| **Router** | A path manager (based on `genro-routes`) that maps URLs to handler functions. |

## Request and Response

| Term | Description |
|------|-------------|
| **Request** | An abstraction of the ASGI scope (`HttpRequest` or `MsgRequest`). |
| **Response** | An object managing the data sent back to the client. |
| **Handler** | A method in an application class that processes a specific route. |
| **Endpoint** | The combination of a route (path) and its associated handler. |

## Infrastructure

| Term | Description |
|------|-------------|
| **Middleware** | A component that intercepts the request/response pipeline. |
| **Storage** | An abstraction for file system access, typically using `LocalStorage`. |
| **Resource** | Any asset (file, template, data) loaded via the `ResourceLoader`. |
| **Lifespan** | The ASGI protocol for managing system startup and shutdown events. |
