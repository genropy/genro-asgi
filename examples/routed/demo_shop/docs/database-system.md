# Database System

Sample Shop implements a **generic SQL database system** with adapter pattern, connection pooling, and transaction management.

## Overview

```mermaid
graph TB
    subgraph "Client Code"
        Shop[Shop Class]
        Tables[Table Managers]
    end

    subgraph "Database Abstraction"
        DB[Database Class]
        Schema[Schema Manager]
    end

    subgraph "Adapter Layer"
        Adapter[Database Adapter]
        SQLiteAdapter[SQLite Adapter]
        PostgresAdapter[PostgreSQL Adapter]
        Adapter --> SQLiteAdapter
        Adapter --> PostgresAdapter
    end

    subgraph "Connection Management"
        Pool[Connection Pool]
        ThreadLocal[Thread-Local Storage]
        Pool --> ThreadLocal
    end

    subgraph "Backend"
        SQLite[(SQLite DB)]
        Postgres[(PostgreSQL DB)]
        SQLiteAdapter --> SQLite
        PostgresAdapter --> Postgres
    end

    Shop --> DB
    Tables --> DB
    DB --> Schema
    DB --> Adapter
    Adapter --> Pool

    style DB fill:#f3e5f5
    style Adapter fill:#fff9c4
    style Pool fill:#e8f5e9
```

## Database Class

The `Database` class is the main interface for database operations.

### Initialization

```python
from sample_shop.sql.database import Database

# SQLite
db = Database("sqlite:shop.db")

# PostgreSQL
db = Database("postgresql://user:pass@localhost/shop")

# In-memory (testing)
db = Database("sqlite::memory:")
```

### Connection String Format

Format: `<dialect>:<connection_info>`

**SQLite**:

- `sqlite:path/to/file.db` - File-based database
- `sqlite::memory:` - In-memory database (testing)

**PostgreSQL**:

- `postgresql://user:password@host:port/database`
- `postgresql://localhost/shop` - Using defaults

### Table Registry

The Database class maintains a registry of table managers:

```python
# Register table
db.register_table("articles", ArticlesTable(db, "articles"))

# Access table
articles = db.table("articles")

# List all tables
table_names = db.table_names()
```

### Schema Management

```python
# Create all tables
db.create_tables()

# Drop all tables (careful!)
db.drop_tables()

# Check if table exists
if db.table_exists("articles"):
    print("Articles table exists")
```

### Direct SQL Execution

For operations not covered by table managers:

```python
# Execute query
results = db.execute("SELECT * FROM articles WHERE price > ?", (100,))

# Execute with named parameters
results = db.execute(
    "SELECT * FROM articles WHERE type_id = :type_id",
    {"type_id": 1}
)

# Execute non-query (INSERT, UPDATE, DELETE)
db.execute("UPDATE articles SET price = price * 1.1 WHERE type_id = ?", (1,))
```

## Database Adapters

Adapters abstract the differences between database backends.

### Adapter Interface

All adapters implement:

```python
class DatabaseAdapter:
    def execute(self, sql: str, params: tuple | dict) -> List[dict]:
        """Execute SQL and return results as list of dicts."""
        ...

    def get_cursor(self):
        """Get a database cursor (thread-safe)."""
        ...

    def close_cursor(self, cursor):
        """Close and return cursor to pool."""
        ...

    def begin_transaction(self):
        """Begin a transaction."""
        ...

    def commit(self):
        """Commit current transaction."""
        ...

    def rollback(self):
        """Rollback current transaction."""
        ...

    def close(self):
        """Close all connections."""
        ...
```

### SQLite Adapter

**Features**:

- File-based or in-memory
- No external dependencies (built into Python)
- Good for development and testing
- Single-writer limitation

**Connection String Examples**:

```python
# File in current directory
db = Database("sqlite:shop.db")

# Absolute path
db = Database("sqlite:/var/data/shop.db")

# Relative path
db = Database("sqlite:../data/shop.db")

# In-memory (data lost on close)
db = Database("sqlite::memory:")
```

**SQLite-Specific Features**:

```python
# Enable foreign keys (off by default in SQLite)
db.execute("PRAGMA foreign_keys = ON")

# Set journal mode
db.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
```

### PostgreSQL Adapter

**Features**:

- Production-ready
- Full ACID compliance
- Concurrent writes
- Advanced features (JSON, arrays, etc.)

**Connection String Examples**:

```python
# Full connection string
db = Database("postgresql://shop_user:password@localhost:5432/shop_db")

# Using defaults (localhost, port 5432, username from env)
db = Database("postgresql:///shop_db")

# With SSL
db = Database("postgresql://user:pass@host/db?sslmode=require")
```

**PostgreSQL-Specific Features**:

```python
# Use RETURNING clause
result = db.execute(
    "INSERT INTO articles (name, price) VALUES (%s, %s) RETURNING id",
    ("Laptop", 999.99)
)
article_id = result[0]["id"]

# JSON operations
db.execute("SELECT data->>'name' FROM articles WHERE data ? 'tags'")
```

## Connection Pooling

Connection pooling ensures efficient and thread-safe database access.

### Thread Safety

Each thread gets its own connection from the pool:

```mermaid
sequenceDiagram
    participant Thread1
    participant Thread2
    participant Pool
    participant Conn1
    participant Conn2

    Thread1->>Pool: get_connection()
    Pool->>Conn1: acquire
    Pool-->>Thread1: connection 1

    Thread2->>Pool: get_connection()
    Pool->>Conn2: acquire
    Pool-->>Thread2: connection 2

    Thread1->>Pool: release_connection()
    Pool->>Conn1: release

    Thread2->>Pool: release_connection()
    Pool->>Conn2: release
```

### Pool Configuration

```python
from sample_shop.sql.database import Database

db = Database(
    "postgresql://localhost/shop",
    pool_size=10,        # Max connections
    max_overflow=5,      # Additional connections if needed
    pool_timeout=30      # Wait timeout in seconds
)
```

### Connection Lifecycle

1. **Acquire**: Thread requests connection from pool
2. **Use**: Thread executes queries using connection
3. **Release**: Thread returns connection to pool
4. **Reuse**: Connection available for other threads

### Benefits

- **Performance**: Reuse existing connections (avoid connection overhead)
- **Thread Safety**: Each thread gets isolated connection
- **Resource Management**: Limit number of open connections
- **Automatic Cleanup**: Connections returned to pool automatically

## Transaction Management

Transactions ensure data consistency and integrity.

### Automatic Transactions

The `DbOpPlugin` automatically manages transactions:

```python
class ArticlesTable(BaseTable):
    @dbop
    def add(self, name: str, price: float, _cursor=None):
        # Transaction started automatically
        _cursor.execute(
            "INSERT INTO articles (name, price) VALUES (?, ?)",
            (name, price)
        )
        # Transaction committed automatically if no error
        return {"success": True}
```

### Transaction Flow

```mermaid
sequenceDiagram
    participant Client
    participant DbOpPlugin
    participant Adapter
    participant Database

    Client->>DbOpPlugin: Call method (write operation)
    DbOpPlugin->>Adapter: get_cursor()
    Adapter->>Database: acquire connection
    Database-->>Adapter: cursor
    DbOpPlugin->>Adapter: begin_transaction()

    alt Success
        DbOpPlugin->>Method: execute
        Method-->>DbOpPlugin: result
        DbOpPlugin->>Adapter: commit()
        DbOpPlugin-->>Client: return result
    else Error
        DbOpPlugin->>Adapter: rollback()
        DbOpPlugin-->>Client: raise exception
    end

    DbOpPlugin->>Adapter: close_cursor()
```

### Manual Transaction Control

For complex operations:

```python
db = Database("sqlite:shop.db")

try:
    cursor = db.get_cursor()
    db.begin_transaction()

    # Multiple operations in same transaction
    cursor.execute("INSERT INTO types (name) VALUES (?)", ("electronics",))
    type_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO articles (type_id, name, price) VALUES (?, ?, ?)",
        (type_id, "Laptop", 999.99)
    )

    db.commit()
except Exception as e:
    db.rollback()
    raise
finally:
    db.close_cursor(cursor)
```

### Transaction Isolation

**SQLite**:

- Default: SERIALIZABLE
- Supports: DEFERRED, IMMEDIATE, EXCLUSIVE

**PostgreSQL**:

- Default: READ COMMITTED
- Supports: READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE

```python
# Set isolation level (PostgreSQL)
db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
```

## Type Conversions

Adapters handle type conversions between Python and SQL.

### Python → SQL

| Python Type | SQLite Type | PostgreSQL Type |
|-------------|-------------|-----------------|
| `int` | INTEGER | INTEGER |
| `float` | REAL | DOUBLE PRECISION |
| `str` | TEXT | VARCHAR |
| `bool` | INTEGER (0/1) | BOOLEAN |
| `datetime` | TEXT (ISO 8601) | TIMESTAMP |
| `date` | TEXT (ISO 8601) | DATE |
| `bytes` | BLOB | BYTEA |
| `None` | NULL | NULL |

### SQL → Python

Results are returned as dictionaries with appropriate Python types:

```python
results = db.execute("SELECT * FROM articles WHERE id = ?", (1,))
# results = [
#     {
#         "id": 1,
#         "name": "Laptop",           # str
#         "price": 999.99,            # float
#         "quantity": 10,             # int
#         "created_at": datetime(...) # datetime
#     }
# ]
```

### Custom Type Handlers

For custom types:

```python
from decimal import Decimal

class CustomAdapter(SQLiteAdapter):
    def convert_to_sql(self, value):
        if isinstance(value, Decimal):
            return float(value)
        return super().convert_to_sql(value)

    def convert_from_sql(self, value, column_type):
        if column_type == "DECIMAL":
            return Decimal(str(value))
        return super().convert_from_sql(value, column_type)
```

## Error Handling

### Database Errors

```python
from sample_shop.sql.errors import (
    DatabaseError,
    ConnectionError,
    QueryError,
    TransactionError
)

try:
    db = Database("postgresql://invalid:connection@localhost/shop")
except ConnectionError as e:
    print(f"Failed to connect: {e}")

try:
    db.execute("INVALID SQL")
except QueryError as e:
    print(f"Query failed: {e}")
```

### Error Hierarchy

```
DatabaseError
├── ConnectionError    # Connection failed
├── QueryError        # SQL execution failed
├── TransactionError  # Transaction failed
└── SchemaError       # Schema creation/migration failed
```

### Retry Logic

For transient errors:

```python
from sample_shop.sql.retry import with_retry

@with_retry(max_attempts=3, backoff=1.5)
def execute_with_retry(db, sql, params):
    return db.execute(sql, params)

# Will retry up to 3 times with exponential backoff
results = execute_with_retry(db, "SELECT * FROM articles", ())
```

## Performance Optimization

### Indexes

Create indexes for frequently queried columns:

```python
db.execute("CREATE INDEX idx_articles_type_id ON articles(type_id)")
db.execute("CREATE INDEX idx_articles_price ON articles(price)")
```

### Query Planning

Analyze query performance:

```python
# SQLite
plan = db.execute("EXPLAIN QUERY PLAN SELECT * FROM articles WHERE type_id = ?", (1,))

# PostgreSQL
plan = db.execute("EXPLAIN ANALYZE SELECT * FROM articles WHERE type_id = $1", (1,))
```

### Batch Operations

For multiple inserts:

```python
# Instead of multiple calls
for article in articles:
    db.table("articles").add(**article)

# Use batch insert
db.execute(
    "INSERT INTO articles (name, price) VALUES (?, ?)",
    [(a["name"], a["price"]) for a in articles],
    batch=True
)
```

### Connection Pool Tuning

```python
db = Database(
    connection_string,
    pool_size=20,           # Increase for high concurrency
    pool_pre_ping=True,     # Test connections before use
    pool_recycle=3600       # Recycle connections after 1 hour
)
```

## Testing

### In-Memory Database

Perfect for unit tests:

```python
def test_articles():
    # Create fresh database for each test
    db = Database("sqlite::memory:")
    db.create_tables()

    # Run tests
    articles = db.table("articles")
    result = articles.add(name="Test", price=9.99, quantity=1)

    assert result["success"] == True
```

### Fixtures

Use pytest fixtures:

```python
import pytest

@pytest.fixture
def db():
    """Provide a fresh database for each test."""
    db = Database("sqlite::memory:")
    db.create_tables()
    yield db
    db.close()

def test_with_fixture(db):
    result = db.table("types").add(name="test")
    assert result["success"] == True
```

### Mock Adapter

For testing without real database:

```python
from unittest.mock import Mock

def test_with_mock():
    mock_adapter = Mock()
    mock_adapter.execute.return_value = [{"id": 1, "name": "Test"}]

    db = Database.__new__(Database)
    db.adapter = mock_adapter

    results = db.execute("SELECT * FROM test")
    assert len(results) == 1
```

## Next Steps

- [Table Managers](table-managers.md) - CRUD operations
- [SmartSwitch Integration](smartswitch-integration.md) - Plugin chain
- [Architecture](architecture.md) - Overall system design
