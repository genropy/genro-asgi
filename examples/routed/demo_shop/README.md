# Demo Shop - smpub Example Application

This is a complete example demonstrating how to use **smpub** to publish a Python application as CLI/HTTP API.

## Structure

```text
demo_shop/
├── sample_shop/       # 📦 Standalone Python library
│   ├── sql/          # Generic database system
│   ├── tables/       # Managers for articles, purchases, etc.
│   ├── shop.py       # Main Shop class
│   ├── example_*.py  # Direct Python usage examples
│   └── test_*.py     # Tests
│
└── published_shop/    # 🚀 App published with smpub
    ├── main.py       # Publisher that exposes Shop via CLI/HTTP
    ├── populate_db.py # Script to populate database
    └── shop.db       # SQLite database
```

## Key Points

### 1. Separation of Concerns

- **sample_shop**: Pure Python library, no smpub dependencies
  - Can be used directly (see `example_pythonic.py`)
  - Has its own tests, documentation, examples
  - Knows nothing about CLI or HTTP

- **published_shop**: Thin layer using smpub to expose sample_shop
  - Imports Shop from sample_shop
  - Publishes it via smpub Publisher
  - Provides CLI and HTTP API automatically

### 2. "Thin Publishing Layer" Philosophy

smpub is not an intrusive framework:

- Your library remains independent
- smpub only adds CLI/HTTP layer
- You can use the library without smpub

## How to Use

### Use sample_shop directly (Pure Python)

```python
from examples.demo_shop.sample_shop.shop import Shop

# Instantiate and use normally
shop = Shop("sqlite:myshop.db")
shop.db.table("types").add(name="electronics", description="Electronic devices")
```

See `sample_shop/example_pythonic.py` for a complete example.

### Use published_shop (CLI/HTTP)

```bash
# Populate database
cd examples/demo_shop/published_shop
python populate_db.py

# Start HTTP server
python main.py
```

Then open browser:

- <http://localhost:8000/> - Homepage with documentation links
- <http://localhost:8000/docs> - Interactive Swagger UI
- <http://localhost:8000/types/list?format=markdown_html> - Types list in rendered markdown

## Supported Formats

All `list()` methods support the `format` parameter:

- `json` - JSON response (default)
- `markdown` - Markdown table (text)
- `html` - HTML table (text)
- `table` - ASCII table (text)
- `markdown_html` - Markdown rendered in browser with marked.js + mermaid.js

Example:

```bash
# JSON
curl http://localhost:8000/articles/list

# Markdown rendered in browser
curl http://localhost:8000/articles/list?format=markdown_html
```

## Demonstrated Features

### SmartSwitch

- Plugin chain (logging → pydantic → dbop)
- Automatic parameter validation with Pydantic
- Automatic database transaction management

### smpub Publisher

- Automatic publishing of Python classes
- CLI/HTTP generation from switcher
- Automatic OpenAPI/Swagger
- Support for sync/async methods

### SQL Database System

- Adapter pattern for SQLite/PostgreSQL
- Table managers with CRUD operations
- Query builder with transaction support
- Thread-safe connection pooling

## Important Files

| File | Description |
|------|-------------|
| `sample_shop/shop.py` | Main Shop class |
| `sample_shop/sql/table.py` | Base class for table managers |
| `sample_shop/tables/*.py` | Managers for articles, purchases, etc. |
| `published_shop/main.py` | smpub Publisher |
| `sample_shop/example_pythonic.py` | Pure Python usage example |

## Next Steps

1. Explore `sample_shop/example_pythonic.py` to see pure Python usage
2. Look at `sample_shop/tables/*.py` to see table managers
3. Read `published_shop/main.py` to understand publisher pattern
4. Start the server and experiment with Swagger UI
5. Try different output formats
