# Genro ASGI

**A minimal, stable ASGI foundation** - framework-agnostic toolkit for building high-performance web services.

[![PyPI version](https://img.shields.io/pypi/v/genro-asgi.svg)](https://pypi.org/project/genro-asgi/)
[![Python Support](https://img.shields.io/pypi/pyversions/genro-asgi.svg)](https://pypi.org/project/genro-asgi/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Overview

Genro ASGI provides a minimal, production-ready ASGI foundation built on Python's standard library. It offers essential components for building web services without the overhead of a full framework.

### Key Features

- **Zero Dependencies**: Built entirely on Python stdlib (optional orjson for fast JSON)
- **Framework-Agnostic**: Use as a foundation or integrate with existing frameworks
- **Production-Ready**: Minimal, tested, and stable
- **Type-Safe**: Full type hints for better IDE support
- **Essential Components**:
  - Core ASGI application
  - Request/Response utilities
  - Lifespan management
  - Essential middleware (CORS, errors, compression, static files)

## Installation

```bash
# Basic installation (stdlib only)
pip install genro-asgi

# With fast JSON support
pip install genro-asgi[json]

# Development installation
pip install genro-asgi[dev]
```

## Quick Start

### Basic Application

```python
from genro_asgi import Application

app = Application()

# Run with uvicorn
# uvicorn app:app
```

### With Request/Response

```python
from genro_asgi import Application, Request, JSONResponse

app = Application()

async def handler(scope, receive, send):
    request = Request(scope)

    # Process request
    data = {"message": "Hello from Genro ASGI", "path": request.path}

    # Send response
    response = JSONResponse(data)
    await response.send(send)
```

### With Middleware

```python
from genro_asgi import Application
from genro_asgi.middleware import CORSMiddleware, ErrorMiddleware

app = Application()

# Wrap with middleware
app = ErrorMiddleware(app, debug=True)
app = CORSMiddleware(app, allow_origins=["*"])
```

### Lifespan Events

```python
from genro_asgi import Application, Lifespan

lifespan = Lifespan()

@lifespan.on_startup
async def startup():
    print("Application starting...")

@lifespan.on_shutdown
async def shutdown():
    print("Application shutting down...")
```

## Architecture

Genro ASGI is designed around these principles:

1. **Minimalism**: Only essential features, nothing more
2. **Composability**: Mix and match components as needed
3. **Stdlib-First**: Avoid external dependencies when possible
4. **Type Safety**: Full type hints throughout

### Core Components

- **Application**: ASGI application core with routing
- **Request**: Convenient access to ASGI scope
- **Response**: Response classes (JSON, HTML, PlainText)
- **Lifespan**: Startup/shutdown event management
- **Middleware**: Essential middleware collection

## Documentation

Full documentation available at: https://genro-asgi.readthedocs.io

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/genropy/genro-asgi.git
cd genro-asgi

# Install in development mode
pip install -e .[dev]
```

### Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=genro_asgi --cov-report=html
```

### Code Quality

```bash
# Format code
black src tests

# Lint code
ruff check .

# Type check
mypy src
```

## License

Copyright 2025 Softwell S.r.l.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Links

- **GitHub**: https://github.com/genropy/genro-asgi
- **PyPI**: https://pypi.org/project/genro-asgi/
- **Documentation**: https://genro-asgi.readthedocs.io
- **Issue Tracker**: https://github.com/genropy/genro-asgi/issues

## Credits

Developed by [Softwell S.r.l.](https://www.softwell.it/)
