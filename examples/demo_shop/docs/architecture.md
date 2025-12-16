# Architecture

Sample Shop follows a **layered architecture** with clear separation of concerns and dependency injection through SmartSwitch.

## System Layers

```mermaid
graph TB
    subgraph "Application Layer"
        Shop[Shop Class]
        PopulateDb[populateDb Method]
    end

    subgraph "Business Logic Layer"
        Tables[Table Managers]
        TypesTable[TypesTable]
        ArticlesTable[ArticlesTable]
        PurchasesTable[PurchasesTable]
        Tables --> TypesTable
        Tables --> ArticlesTable
        Tables --> PurchasesTable
    end

    subgraph "Data Access Layer"
        Database[Database Class]
        BaseTable[BaseTable]
        TypesTable --> BaseTable
        ArticlesTable --> BaseTable
        PurchasesTable --> BaseTable
    end

    subgraph "Infrastructure Layer"
        Adapter[Database Adapter]
        Pool[Connection Pool]
        SQLite[SQLite Backend]
        Postgres[PostgreSQL Backend]
        Adapter --> Pool
        Pool --> SQLite
        Pool --> Postgres
    end

    subgraph "Cross-Cutting"
        Switcher[SmartSwitch]
        Plugins[Plugin Chain]
        Switcher --> Plugins
    end

    Shop --> Database
    Database --> Adapter
    Database -.creates.-> Tables
    BaseTable --> Switcher
    Switcher -.injects.-> BaseTable

    style Shop fill:#e1f5fe
    style Database fill:#f3e5f5
    style BaseTable fill:#e8f5e9
    style Adapter fill:#fff9c4
    style Switcher fill:#fff3e0
```

## Core Components

### 1. Shop Class

**Purpose**: Main entry point and orchestrator

**Responsibilities**:

- Initialize database connection
- Provide access to table managers
- Coordinate complex operations (like `populateDb`)
- Maintain application state

**Key Methods**:

- `__init__(connection_string)` - Initialize with database connection
- `populateDb()` - Populate with sample data
- Access to `shop.db.table(name)` for table managers

```python
class Shop:
    def __init__(self, connection_string: str):
        self.db = Database(connection_string)
        self._setup_tables()

    def populateDb(self):
        # Populate with sample data
        ...
```

### 2. Database Class

**Purpose**: Database abstraction and table registry

**Responsibilities**:

- Create and configure database adapter
- Register and provide access to table managers
- Schema management
- Transaction coordination

**Key Methods**:

- `table(name)` - Get table manager by name
- `create_tables()` - Initialize database schema
- `execute()` - Direct SQL execution

```python
class Database:
    def __init__(self, connection_string: str):
        self.adapter = self._create_adapter(connection_string)
        self._tables = {}

    def table(self, name: str) -> BaseTable:
        return self._tables[name]
```

### 3. Table Managers

**Purpose**: CRUD operations for specific tables

**Responsibilities**:

- Define table schema
- Implement business logic for table operations
- Use SmartSwitch for method dispatch
- Validate input with Pydantic

**Base Class**:

```python
class BaseTable:
    __slots__ = ('db', 'table_name', 'switcher')

    dbop = Switcher(
        prefix='',
        plugins=[
            LoggingPlugin(),
            PydanticPlugin(),
            DbOpPlugin()  # Injects cursor
        ]
    )

    def __init__(self, db: Database, table_name: str):
        self.db = db
        self.table_name = table_name
```

**Derived Classes**:

- `TypesTable` - Product types/categories
- `ArticlesTable` - Products with inventory
- `PurchasesTable` - Purchase orders

### 4. Database Adapter

**Purpose**: Abstract database backend differences

**Responsibilities**:

- Connection pooling (thread-safe)
- SQL dialect translation
- Type conversions
- Transaction management

**Supported Backends**:

- SQLite (file-based, development)
- PostgreSQL (production)

```python
class DatabaseAdapter:
    def execute(self, sql: str, params: dict) -> List[dict]:
        ...

    def begin_transaction(self):
        ...

    def commit(self):
        ...

    def rollback(self):
        ...
```

## SmartSwitch Integration

SmartSwitch provides **method dispatch with plugin chain**:

```mermaid
graph LR
    Method[Method Call] --> Switcher
    Switcher --> LogPlugin[Logging Plugin]
    LogPlugin --> PydPlugin[Pydantic Plugin]
    PydPlugin --> DbPlugin[DbOp Plugin]
    DbPlugin --> Handler[Method Handler]
    Handler --> DbPlugin
    DbPlugin --> PydPlugin
    PydPlugin --> LogPlugin
    LogPlugin --> Result[Return Result]

    style Switcher fill:#fff3e0
    style LogPlugin fill:#e3f2fd
    style PydPlugin fill:#f3e5f5
    style DbPlugin fill:#e8f5e9
```

### Plugin Chain

1. **LoggingPlugin** - Logs method entry/exit and timing
2. **PydanticPlugin** - Validates and converts parameters
3. **DbOpPlugin** - Injects database cursor into method

### DbOpPlugin Details

The **DbOpPlugin** is the key to the data access pattern:

**Pre-call**:

- Gets database cursor from adapter
- Injects cursor into method kwargs as `_cursor`
- Begins transaction (if write operation)

**Post-call**:

- Commits transaction (if success)
- Rollbacks transaction (if error)
- Closes cursor
- Returns result

**Example**:

```python
class ArticlesTable(BaseTable):
    @dbop
    def add(self, name: str, price: float, _cursor=None):
        # _cursor is injected by DbOpPlugin
        _cursor.execute(
            "INSERT INTO articles (name, price) VALUES (?, ?)",
            (name, price)
        )
        return {"id": _cursor.lastrowid}
```

## Data Flow

### Read Operation (list)

```mermaid
sequenceDiagram
    participant Client
    participant Switcher
    participant Pydantic
    participant DbOp
    participant Method
    participant Adapter
    participant DB

    Client->>Switcher: articles.list(type_id=1)
    Switcher->>Pydantic: pre_call
    Pydantic->>Pydantic: validate type_id
    Pydantic->>DbOp: pre_call
    DbOp->>Adapter: get_cursor()
    Adapter->>DB: acquire connection
    DB-->>Adapter: cursor
    Adapter-->>DbOp: cursor
    DbOp->>Method: call(type_id=1, _cursor=cursor)
    Method->>Adapter: execute SELECT
    Adapter->>DB: query
    DB-->>Adapter: rows
    Adapter-->>Method: results
    Method-->>DbOp: list of articles
    DbOp->>Adapter: close_cursor()
    DbOp-->>Pydantic: post_call
    Pydantic-->>Switcher: post_call
    Switcher-->>Client: return results
```

### Write Operation (add)

```mermaid
sequenceDiagram
    participant Client
    participant Switcher
    participant Pydantic
    participant DbOp
    participant Method
    participant Adapter
    participant DB

    Client->>Switcher: articles.add(name="Laptop", price=999.99)
    Switcher->>Pydantic: pre_call
    Pydantic->>Pydantic: validate parameters
    Pydantic->>DbOp: pre_call
    DbOp->>Adapter: get_cursor()
    Adapter->>DB: acquire connection
    DB-->>Adapter: cursor
    Adapter-->>DbOp: cursor
    DbOp->>Adapter: begin_transaction()
    DbOp->>Method: call(name, price, _cursor=cursor)
    Method->>Adapter: execute INSERT
    Adapter->>DB: insert
    DB-->>Adapter: lastrowid
    Adapter-->>Method: id
    Method-->>DbOp: {"id": 123, "success": true}
    DbOp->>Adapter: commit()
    DbOp->>Adapter: close_cursor()
    DbOp-->>Pydantic: post_call
    Pydantic-->>Switcher: post_call
    Switcher-->>Client: return result
```

## Design Patterns

### 1. Adapter Pattern

**Problem**: Support multiple database backends with different APIs

**Solution**: Database adapter abstracts backend differences

**Benefits**:

- Swap databases without changing business logic
- Unified API for all operations
- Easy to add new backends

### 2. Registry Pattern

**Problem**: Dynamically access table managers by name

**Solution**: Database class maintains table registry

**Benefits**:

- Dynamic table access: `db.table("articles")`
- Centralized table management
- Easy to add new tables

### 3. Dependency Injection

**Problem**: Methods need database access

**Solution**: DbOpPlugin injects cursor via SmartSwitch

**Benefits**:

- Clean method signatures
- Automatic transaction management
- Testable (can inject mock cursor)

### 4. Plugin Chain (Aspect-Oriented)

**Problem**: Cross-cutting concerns (logging, validation, transactions)

**Solution**: SmartSwitch plugin chain

**Benefits**:

- Separation of concerns
- Reusable plugins
- Composable behavior

## Configuration

### Database Connection String

Format: `<dialect>:<location>`

**SQLite**:

```python
# File-based
Shop("sqlite:/path/to/db.db")
Shop("sqlite:shop.db")

# In-memory (testing)
Shop("sqlite::memory:")
```

**PostgreSQL**:

```python
Shop("postgresql://user:password@host:port/database")
Shop("postgresql://shop_user:pass@localhost:5432/shop_db")
```

### Thread Safety

- Connection pooling ensures thread-safe operations
- Each thread gets its own connection
- Transactions are isolated per connection

## Error Handling

### Database Errors

- Connection errors raise `DatabaseConnectionError`
- Query errors raise `DatabaseQueryError`
- Transaction errors automatically rollback

### Validation Errors

- Pydantic validates all parameters
- Invalid types raise `ValidationError`
- Missing required fields raise `ValidationError`

### Plugin Chain Error Flow

```mermaid
sequenceDiagram
    participant Method
    participant DbOp
    participant Pydantic
    participant Switcher

    Method->>DbOp: raise DatabaseError
    DbOp->>DbOp: rollback transaction
    DbOp->>Pydantic: propagate error
    Pydantic->>Switcher: propagate error
    Switcher-->>Client: raise exception
```

## Extensibility

### Adding New Tables

1. Create table manager class inheriting from `BaseTable`
2. Define schema
3. Implement CRUD methods decorated with `@dbop`
4. Register in `Database._setup_tables()`

```python
class CustomTable(BaseTable):
    dbop = Switcher(prefix='', plugins=[...])

    def create_schema(self):
        return """
        CREATE TABLE IF NOT EXISTS custom (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
        """

    @dbop
    def add(self, name: str, _cursor=None):
        _cursor.execute(
            "INSERT INTO custom (name) VALUES (?)",
            (name,)
        )
        return {"id": _cursor.lastrowid}
```

### Adding New Plugins

Extend the plugin chain in `BaseTable`:

```python
dbop = Switcher(
    prefix='',
    plugins=[
        LoggingPlugin(),
        PydanticPlugin(),
        CachingPlugin(),      # New plugin
        DbOpPlugin()
    ]
)
```

### Adding New Backends

Implement database adapter interface:

```python
class MySQLAdapter(DatabaseAdapter):
    def __init__(self, connection_string: str):
        # MySQL-specific initialization
        ...

    def execute(self, sql: str, params: dict):
        # MySQL-specific execution
        ...
```

## Performance Considerations

### Connection Pooling

- Reuse connections across requests
- Configurable pool size
- Automatic connection lifecycle management

### Query Optimization

- Use parameterized queries (prevent SQL injection)
- Index foreign keys
- Batch operations where possible

### Transaction Management

- Write operations use transactions
- Read operations can be non-transactional
- Configurable isolation levels

## Testing Strategy

### Unit Tests

- Test table managers in isolation
- Mock database cursor
- Test validation logic

### Integration Tests

- Test with real database (SQLite :memory:)
- Test transaction rollback
- Test error handling

### Example Test

```python
def test_articles_add():
    shop = Shop("sqlite::memory:")
    result = shop.db.table("articles").add(
        type_id=1,
        name="Test Product",
        price=99.99,
        quantity=5
    )
    assert result["success"] == True
    assert "id" in result
```

## Next Steps

- [Database System](database-system.md) - Deep dive into database layer
- [Table Managers](table-managers.md) - CRUD operations in detail
- [SmartSwitch Integration](smartswitch-integration.md) - Plugin chain explained
