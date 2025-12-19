# Routing

**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-14
**genro-routes version**: 0.10.0

---

## Overview

genro-asgi delegates all routing to **genro-routes**, a separate library that provides tree-based routing with introspection capabilities.

> **Full documentation**: [genro-routes](https://github.com/genropy/genro-routes)

---

## Core Components

| Component | Description |
|-----------|-------------|
| `Router` | Tree-based router, organizes handlers hierarchically |
| `RoutingClass` | Base class for classes with routed methods |
| `@route(name)` | Decorator to register methods as routes |
| `RouterInterface` | Protocol for custom routers (e.g., `StaticRouter`) |

---

## Key Methods

| Method | Description |
|--------|-------------|
| `router.get(selector)` | Resolve path to handler |
| `router.nodes(**kwargs)` | List all nodes (entries + sub-routers) |
| `router.attach(router, name)` | Attach a sub-router |
| `router.attach_instance(obj, name)` | Attach a routed instance |
| `router.openapi()` | Generate OpenAPI schema |
| `router.plug(plugin)` | Register a plugin |

---

## Path Resolution

Paths use `/` as separator (URL-style, same as HTTP paths):

```python
# URL path is used directly as selector
"/" → "index"
"/docs" → "docs"
"/docs/api/users" → "docs/api/users"
"/_sys/status" → "_sys/status"
```

No conversion needed between URL paths and selectors.

---

## Basic Usage

### Routed Methods

```python
from genro_routes import RoutingClass, Router, route

class MyApp(RoutingClass):
    def __init__(self):
        self.router = Router(self, name="app")

    @route("app")
    def index(self):
        return {"status": "ok"}

    @route("app")
    def users(self, id: str = None):
        if id:
            return {"user": id}
        return {"users": ["alice", "bob"]}
```

### Attaching Sub-Routers

```python
from genro_asgi.routers import StaticRouter

# Attach a StaticRouter for serving files
static = StaticRouter("./public", name="static")
self.router.attach(static, name="static")

# Now /static/style.css serves ./public/style.css
```

### Attaching Instances

```python
class DocsApp(RoutingClass):
    def __init__(self):
        self.router = Router(self, name="docs")

    @route("docs")
    def index(self):
        return {"docs": "welcome"}

# In server
docs = DocsApp()
server.router.attach_instance(docs, name="docs")

# Now /docs/index calls docs.index()
```

---

## Introspection with nodes()

The `nodes()` method returns the router tree structure:

```python
# Get all nodes
nodes = router.nodes()

# With mode parameter for different output formats
nodes = router.nodes(mode="flat")    # flat list of all entries
nodes = router.nodes(mode="tree")    # nested tree structure
nodes = router.nodes(mode="openapi") # OpenAPI-compatible format

# Lazy loading for large trees
nodes = router.nodes(lazy=True)
```

---

## FilterPlugin

Tag-based filtering with boolean expressions:

```python
from genro_routes import FilterPlugin

# Register plugin
router.plug(FilterPlugin())

# Tag routes using decorators or metadata
@route("app", tags=["api", "public"])
def public_endpoint(self):
    pass

@route("app", tags=["api", "internal"])
def internal_endpoint(self):
    pass

# Filter nodes
public_nodes = router.nodes(filter="api & public")
non_internal = router.nodes(filter="api & !internal")
```

### Future: User-Based Filtering

FilterPlugin can be used to enable/disable routes based on current user's permissions:

```python
# TODO: Future implementation
# Filter routes based on user tags/roles
user_tags = request.user.tags  # e.g., ["admin", "editor"]
visible_nodes = router.nodes(filter=build_filter_from_tags(user_tags))
```

This allows dynamic route visibility based on user permissions without modifying route definitions.

---

## OpenAPI Generation

```python
# Generate OpenAPI schema
schema = router.openapi()

# Returns dict compatible with OpenAPI 3.0 spec
# Can be serialized to JSON/YAML
```

---

## StaticRouter

genro-asgi provides `StaticRouter` that implements `RouterInterface` for serving static files:

```python
from genro_asgi.routers import StaticRouter

# Create router for a directory
static = StaticRouter("./public", name="assets")

# Resolves paths to files
handler = static.get("css/style.css")  # returns file handler

# List contents
nodes = static.nodes()  # returns files and subdirectories
```

See [StaticRouter documentation](../api/static_router.md) for details.

---

## Integration with AsgiServer

`AsgiServer` inherits from `RoutingClass` and uses genro-routes for dispatch:

```python
from genro_asgi import AsgiServer
from genro_routes import route

class MyServer(AsgiServer):
    @route("root")
    def index(self):
        return {"message": "Hello"}

    @route("root")
    def api(self, path: str = None):
        return {"api": path}
```

The `Dispatcher` class handles the routing:

1. Receives HTTP request with path (e.g., `/api/users`)
2. Calls `router.get("api/users")` to find handler
3. Executes handler and converts result to Response

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
