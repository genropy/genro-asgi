# Sample Shop - E-Commerce Library

**Sample Shop** is a complete e-commerce library demonstrating how to build a well-structured Python application using **SmartSwitch** for method dispatch and a flexible SQL database system.

```{note}
This library is **completely independent** from smartpublisher. It uses SmartSwitch for clean API design, making it easy to publish later (see `published_shop/` for the trivial ~20 line publishing layer).
```

## What is Sample Shop?

Sample Shop is a **standalone Python library** that implements:

- **SQL Database System** - Generic adapter pattern for SQLite/PostgreSQL
- **Table Managers** - CRUD operations with Pydantic validation
- **SmartSwitch Integration** - Clean method dispatch with plugin chain
- **Shop Class** - High-level API for e-commerce operations

## Architecture Overview

```mermaid
graph TB
    subgraph "Shop - Main Entry Point"
        Shop[Shop Class]
    end

    subgraph "Database Layer"
        DB[Database]
        Adapter[DB Adapter]
        Pool[Connection Pool]
        DB --> Adapter
        Adapter --> Pool
    end

    subgraph "Table Managers"
        Types[TypesTable]
        Articles[ArticlesTable]
        Purchases[PurchasesTable]
        BaseTable[BaseTable]
        Types --> BaseTable
        Articles --> BaseTable
        Purchases --> BaseTable
    end

    subgraph "SmartSwitch Plugin Chain"
        Logging[LoggingPlugin]
        Pydantic[PydanticPlugin]
        DbOp[DbOpPlugin]
        Logging --> Pydantic
        Pydantic --> DbOp
    end

    Shop --> DB
    DB -.manages.-> Types
    DB -.manages.-> Articles
    DB -.manages.-> Purchases
    BaseTable --> DbOp

    style Shop fill:#e1f5fe
    style DB fill:#f3e5f5
    style BaseTable fill:#e8f5e9
    style DbOp fill:#fff3e0
```

## Key Features

### 1. Database Adapter Pattern

Support for multiple database backends with a unified API:

```python
# SQLite
shop = Shop("sqlite:shop.db")

# PostgreSQL
shop = Shop("postgresql://user:pass@localhost/shopdb")
```

The adapter handles:

- Connection pooling (thread-safe)
- Transaction management
- Type conversions
- SQL dialect differences

### 2. Table Managers

Each table has a dedicated manager class:

- **TypesTable** - Product categories
- **ArticlesTable** - Products with inventory
- **PurchasesTable** - Purchase orders

All managers provide:

- `add()` - Insert records
- `list()` - Query with filters
- `update()` - Modify records
- `delete()` - Remove records
- `count()` - Count records

### 3. SmartSwitch Plugin Chain

Methods are dispatched through a plugin chain:

```mermaid
sequenceDiagram
    participant Client
    participant Switcher
    participant LogPlugin
    participant PydanticPlugin
    participant DbOpPlugin
    participant Method

    Client->>Switcher: Call method
    Switcher->>LogPlugin: Pre-call
    LogPlugin->>PydanticPlugin: Pre-call
    PydanticPlugin->>DbOpPlugin: Pre-call (validated)
    DbOpPlugin->>Method: Execute (with cursor)
    Method-->>DbOpPlugin: Result
    DbOpPlugin-->>PydanticPlugin: Post-call
    PydanticPlugin-->>LogPlugin: Post-call
    LogPlugin-->>Switcher: Post-call
    Switcher-->>Client: Return result
```

**Plugin Responsibilities**:

- **LoggingPlugin**: Logs method calls and timing
- **PydanticPlugin**: Validates parameters with Pydantic
- **DbOpPlugin**: Provides database cursor and transaction management

### 4. Format Negotiation

All `list()` methods support multiple output formats:

| Format | Description | Use Case |
|--------|-------------|----------|
| `json` | JSON list (default) | API responses |
| `markdown` | Markdown table | Documentation |
| `html` | HTML table | Reports |
| `table` | ASCII table | Terminal output |

```python
# JSON (default)
types = shop.db.table("types").list()

# Markdown table
types_md = shop.db.table("types").list(format="markdown")

# HTML table
types_html = shop.db.table("types").list(format="html")
```

## Quick Start

### Installation

Sample Shop requires Python 3.10+ and [SmartSwitch](https://smartswitch.readthedocs.io):

```bash
pip install smartswitch pydantic
```

### Basic Usage

```python
from sample_shop.shop import Shop

# Create shop instance
shop = Shop("sqlite:shop.db")

# Add a product type
shop.db.table("types").add(
    name="electronics",
    description="Electronic devices"
)

# Add a product
shop.db.table("articles").add(
    type_id=1,
    name="Laptop",
    description="15-inch laptop",
    price=999.99,
    quantity=10
)

# List products
articles = shop.db.table("articles").list()
print(articles)

# Query with filters
electronics = shop.db.table("articles").list(type_id=1)
```

### Populate Sample Data

Use the provided population script:

```python
shop = Shop("sqlite:shop.db")
shop.populateDb()
```

This creates sample types, articles, and purchases for testing.

## Documentation Structure

```{toctree}
:maxdepth: 2
:caption: Core Concepts

architecture
database-system
table-managers
smartswitch-integration
```

## Publishing with smpub

Sample Shop is designed to be **easily published** using smpub. The `published_shop/` directory contains a minimal publishing layer (~20 lines):

```python
from smartpublisher import Publisher
from sample_shop.shop import Shop

class PublishedShop(Publisher):
    def on_init(self):
        shop = Shop("sqlite:shop.db")
        self.publish("types", shop.db.table("types"), switcher_name="dbop")
        self.publish("articles", shop.db.table("articles"), switcher_name="dbop")
        self.publish("purchases", shop.db.table("purchases"), switcher_name="dbop")
```

This automatically provides:

- **CLI interface**: `python main.py articles list`
- **HTTP API**: `http://localhost:8000/articles/list`
- **OpenAPI docs**: `http://localhost:8000/docs`

Learn more at [smpub documentation](https://smpub.readthedocs.io).

## Learn More

- [Architecture Deep Dive](architecture.md) - Understand the design
- [Database System](database-system.md) - Learn the SQL layer
- [Table Managers](table-managers.md) - CRUD operations
- [SmartSwitch Integration](smartswitch-integration.md) - Plugin chain

## License

MIT License - Sample code for demonstration purposes.

## Links

- [smpub Framework](https://smpub.readthedocs.io)
- [SmartSwitch](https://smartswitch.readthedocs.io)
- [GitHub Repository](https://github.com/genropy/smartpublisher)
