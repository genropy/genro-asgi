"""
Source of truth for SqlDb, the thread-safe database manager with adapter pattern.

Recreate from this contract if wiped:

- Responsibilities:
    * Manage a thread-local connection via adapters (SQLite, Postgres).
    * Register table manager classes and expose them via ``table(name)``.
    * Provide transaction helpers (cursor, commit, rollback).
    * Delegate schema creation/verification to the adapter.

- Constructor: ``SqlDb(connection_string: str, app: Any)``
    * Stores ``app``.
    * Parses the connection string ``"<type>:<info>"`` via ``get_adapter``;
      raises on invalid format or unknown type.
    * Maintains thread-local storage for connections.
    * Initializes ``self.tables`` as an empty dict.

- add_table(table_class):
    * Requires ``_table_name``; optional ``_registry_name`` overrides the key.
    * Instantiates the table with ``self`` and stores it in ``self.tables[name]``.

- table(name):
    * Returns previously registered table instance or raises ValueError if missing.

- connection / cursor / commit / rollback:
    * ``connection`` lazily opens adapter connection per thread; ``cursor`` uses
      adapter.cursor(); commit/rollback delegate to adapter.

- get_adapter(connection_string):
    * Splits on first ':' into ``db_type`` and ``connection_info``.
    * Looks up ``ADAPTERS[db_type]``, instantiates with ``connection_info`` and self.
    * Raises ValueError for malformed strings; KeyError propagates if type unknown.

Adapters must provide connect(), cursor(), commit(), rollback(), checkStructure().
"""

import threading

from .adapters import ADAPTERS, DbAdapter


class SqlDb:
    """
    Thread-safe database manager with adapter pattern for multiple backends.

    Supports multiple database types via adapters:
    - SQLite: connection string format "sqlite:path/to/db.sqlite"
    - PostgreSQL: connection string format "postgres:postgresql://user:pass@host/db"

    Features:
    - Thread-local connection management (each thread gets its own connection)
    - Table class registration via add_table()
    - Table access via table(name) with lazy instantiation
    - Transaction management via commit()/rollback()
    - Schema creation and verification

    Usage:
        # Initialize with connection string and app reference
        db = SqlDb("sqlite:shop.db", app)

        # Register table classes
        db.add_table(ArticleTypes)
        db.add_table(Articles)
        db.checkStructure()

        # Access tables and perform operations
        db.table('types').add("electronics", "...", autocommit=True)

        # Manual transaction management
        db.table('types').add("shoes", autocommit=False)
        db.table('types').add("clothing", autocommit=False)
        db.commit()  # Atomic commit of both operations

        # Rollback on error
        try:
            db.table('types').add("invalid", autocommit=False)
            db.commit()
        except Exception:
            db.rollback()
    """

    def __init__(self, connection_string, app):
        """
        Initialize database manager.

        Args:
            connection_string: Database connection string in format "type:connection_info"
                             Examples: "sqlite:shop.db", "postgres:postgresql://..."
            app: Application instance (Shop)
        """
        self.app = app
        self._thread_local = threading.local()

        try:
            self.adapter = self.get_adapter(connection_string)
        except (ValueError, KeyError, RuntimeError) as e:
            raise RuntimeError(f"Failed to initialize database: {e}")

        # Table instances
        self.tables = {}  # name -> table_instance

    def add_table(self, table_class):
        """
        Register and instantiate a table class.

        Args:
            table_class: Table manager class (must have _table_name attribute)
        """
        if not hasattr(table_class, "_table_name"):
            raise ValueError(f"Table class {table_class.__name__} must have _table_name attribute")

        # Use _registry_name if present, otherwise _table_name
        name = getattr(table_class, "_registry_name", None) or table_class._table_name
        instance = table_class(self)
        self.tables[name] = instance

    def table(self, name):
        """
        Get table instance by name.

        Args:
            name: Table name

        Returns:
            Table instance

        Raises:
            ValueError: If table not registered
        """
        try:
            return self.tables[name]
        except KeyError:
            raise ValueError(f"Table '{name}' not registered. Use add_table() first.")

    @property
    def connection(self):
        """
        Get or create database connection for current thread.

        Returns:
            Database connection object (thread-local)
        """
        if not hasattr(self._thread_local, "conn") or self._thread_local.conn is None:
            self._thread_local.conn = self.adapter.connect()
        return self._thread_local.conn

    def cursor(self):
        """
        Get a cursor from the current thread's connection.

        Returns:
            Database cursor
        """
        return self.adapter.cursor()

    def commit(self):
        """Commit current thread's database connection."""
        self.adapter.commit()

    def rollback(self):
        """Rollback current thread's database connection."""
        self.adapter.rollback()

    def get_adapter(self, connection_string: str) -> DbAdapter:
        """
        Parse connection string and create appropriate adapter.

        Args:
            connection_string: Database connection string in format "type:connection_info"
                             Examples: "sqlite:shop.db", "postgres:postgresql://..."

        Returns:
            Initialized database adapter

        Raises:
            ValueError: If connection string format is invalid or db type unsupported
        """
        # Parse connection string and create adapter
        try:
            db_type, connection_info = connection_string.split(":", 1)
        except ValueError:
            raise ValueError(
                f"Invalid connection string format: '{connection_string}'. "
                f"Expected format: 'type:connection_info' (e.g., 'sqlite:shop.db')"
            )

        adapter_class = ADAPTERS[db_type]
        adapter = adapter_class(connection_info, self)

        return adapter
