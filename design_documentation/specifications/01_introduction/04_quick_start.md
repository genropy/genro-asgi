# Quick Start for Contributors

This guide helps you set up a development environment and understand the codebase structure to contribute to genro-asgi.

## Prerequisites

- Python 3.10 or higher
- Git
- A virtual environment tool (venv, virtualenv, or similar)

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/genropy/genro-asgi.git
cd genro-asgi
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows
```

### 3. Install in Development Mode

```bash
pip install -e ".[dev]"
```

This installs:

- genro-asgi in editable mode
- All runtime dependencies (genro-routes, genro-toolbox, genro-tytx, etc.)
- Development tools (pytest, ruff, mypy, black)

### 4. Verify Installation

```bash
# Run tests
pytest

# Type checking
mypy src

# Linting
ruff check src
```

## Project Structure

```text
genro-asgi/
├── src/genro_asgi/           # Source code
│   ├── __init__.py           # Package exports
│   ├── server.py             # AsgiServer - main entry point
│   ├── application.py        # AsgiApplication - base class
│   ├── dispatcher.py         # Request dispatcher
│   ├── request.py            # Request classes (HttpRequest, MsgRequest)
│   ├── response.py           # Response builder
│   ├── server_config.py      # Configuration parser
│   ├── lifespan.py           # Startup/shutdown handling
│   ├── storage.py            # LocalStorage filesystem access
│   ├── resources.py          # ResourceLoader
│   ├── loader.py             # AppLoader for isolated imports
│   ├── exceptions.py         # HTTP exceptions
│   ├── types.py              # ASGI type definitions
│   ├── websocket.py          # WebSocket handling
│   ├── middleware/           # Middleware implementations
│   │   ├── __init__.py       # middleware_chain factory
│   │   ├── authentication.py # AuthMiddleware
│   │   ├── cors.py           # CORSMiddleware
│   │   ├── errors.py         # ErrorMiddleware
│   │   ├── compression.py    # CompressionMiddleware
│   │   ├── logging.py        # LoggingMiddleware
│   │   └── cache.py          # CacheMiddleware
│   ├── datastructures/       # HTTP data structures
│   │   ├── headers.py        # Headers
│   │   ├── query_params.py   # QueryParams
│   │   ├── url.py            # URL
│   │   ├── state.py          # State
│   │   └── address.py        # Address
│   ├── executors/            # Thread/Process executors
│   │   ├── base.py           # BaseExecutor
│   │   ├── local.py          # LocalExecutor
│   │   └── registry.py       # ExecutorRegistry
│   ├── wsx/                   # WebSocket extensions
│   │   ├── protocol.py       # WSX RPC protocol
│   │   └── registry.py       # Connection registry
│   ├── routers/              # Specialized routers
│   │   └── static_router.py  # Static file serving
│   ├── authentication/       # Auth backends
│   │   └── base.py           # Authentication base classes
│   ├── utils/                # Utilities
│   │   └── binder.py         # ServerBinder
│   └── resources/            # Framework resources
│       └── html/             # Default HTML pages
├── tests/                    # Test suite
├── examples/                 # Example applications
├── design_documentation/     # Design specs (this folder)
└── pyproject.toml            # Package configuration
```

## Key Files to Understand

### Entry Point: server.py

```python
# src/genro_asgi/server.py
class AsgiServer(RoutingClass):
    """The main orchestrator."""

    def __init__(self, server_dir=None, ...):
        self.config = ServerConfig(...)
        self.router = Router(self, name="root")
        self.apps = {}
        # ... mount apps, build middleware chain

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
        else:
            await self.dispatcher(scope, receive, send)
```

### Application Base: application.py

```python
# src/genro_asgi/application.py
class AsgiApplication(RoutingClass):
    """Base for all mountable apps."""

    openapi_info: ClassVar[dict] = {}

    def __init__(self, **kwargs):
        self.main = Router(self, name="main")
        self.on_init(**kwargs)

    def on_startup(self): pass
    def on_shutdown(self): pass
```

### Request Flow: dispatcher.py

```python
# src/genro_asgi/dispatcher.py
class Dispatcher:
    async def __call__(self, scope, receive, send):
        # 1. Create request
        request = self.server.request_registry.create(scope, receive, send)
        # 2. Find handler via router
        node = self.server.router.node(path, auth_tags=...)
        # 3. Execute handler
        result = await smartasync(node)(**query_params)
        # 4. Send response
        await request.response.set_result(result)
```

## Creating a Test Application

Create `examples/test_app/main.py`:

```python
from genro_asgi import AsgiApplication
from genro_routes import route


class TestApp(AsgiApplication):
    openapi_info = {
        "title": "Test API",
        "version": "1.0.0",
    }

    @route("main")
    def hello(self, name: str = "World"):
        return {"message": f"Hello, {name}!"}

    @route("main")
    def echo(self, data: dict | None = None):
        return {"received": data}
```

Create `examples/test_app/config.yaml`:

```yaml
server:
  host: "127.0.0.1"
  port: 8000
  reload: true

middleware:
  errors: on
  cors: on

apps:
  test:
    module: "main:TestApp"
```

Run it:

```bash
cd examples/test_app
python -m genro_asgi serve .
```

Test:

```bash
curl http://localhost:8000/test/hello
# {"message": "Hello, World!"}

curl http://localhost:8000/test/hello?name=Developer
# {"message": "Hello, Developer!"}
```

## Running Tests

### All Tests

```bash
pytest
```

### Specific Test File

```bash
pytest tests/test_server.py
```

### With Coverage

```bash
pytest --cov=genro_asgi --cov-report=html
# Open htmlcov/index.html in browser
```

### Verbose Output

```bash
pytest -v tests/test_request.py::test_http_request_path
```

## Code Quality Checks

### Before Committing

```bash
# Format code
black src tests

# Check linting
ruff check src tests

# Type checking
mypy src

# Run tests
pytest
```

### Git Hooks

The project uses git hooks for pre-commit and pre-push validation.

Check hooks exist:

```bash
ls -la .git/hooks/pre-commit .git/hooks/pre-push
```

## Common Development Tasks

### Adding a New Middleware

1. Create `src/genro_asgi/middleware/your_middleware.py`
2. Follow the ASGI middleware pattern:

```python
class YourMiddleware:
    def __init__(self, app, **config):
        self.app = app
        # store config

    async def __call__(self, scope, receive, send):
        # Pre-processing
        await self.app(scope, receive, send)
        # Post-processing (if needed)
```

3. Register in `middleware/__init__.py`
4. Add tests in `tests/test_your_middleware.py`

### Adding a New Data Structure

1. Create `src/genro_asgi/datastructures/your_struct.py`
2. Export in `datastructures/__init__.py`
3. Add to `__all__` in main `__init__.py`
4. Add tests

### Modifying Request/Response

1. Understand existing flow in `request.py` / `response.py`
2. Follow the instance-scoped pattern (no globals)
3. Add tests for new functionality
4. Update `__all__` exports if adding public API

## Understanding the Routing System

genro-routes is instance-scoped, not blueprint-based:

```python
# Each instance has its own router
class MyApp(AsgiApplication):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # Creates self.main
        # Optional: additional routers
        self.admin = Router(self, name="admin")

    @route("main")  # Routes to self.main
    def public_endpoint(self):
        return {"public": True}

    @route("admin", auth_tags="admin")  # Routes to self.admin
    def admin_endpoint(self):
        return {"admin": True}
```

## Getting Help

- **Documentation**: `design_documentation/` folder
- **Issues**: GitHub issues
- **Code Search**: Use grep/IDE to find implementations

## Next Steps

1. Read [Core Principles](02_core_principles.md) to understand architectural decisions
2. Explore [Terminology](03_terminology.md) for component definitions
3. Study existing tests in `tests/` for patterns
4. Pick a good first issue from GitHub

## Related Documents

- [Vision and Goals](01_vision_and_goals.md) - Project overview
- [Core Principles](02_core_principles.md) - Architectural principles
- [Terminology](03_terminology.md) - Glossary of terms
- [Server Architecture](../02_server_foundation/01_server_architecture.md) - Detailed server design
