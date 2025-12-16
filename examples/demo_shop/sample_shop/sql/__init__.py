"""
Source of truth for SQL utilities in the demo shop.

Exports:
- ``SqlDb``: thread-safe DB manager with adapters (see sqldb.py contract).
- ``Table``: table base class with Column-based schema and router+plugins.
- ``Column``: column definition class for table schema.
- Type constants: ``Integer``, ``String``, ``Float``, ``Boolean``, ``Timestamp``, ``Blob``.
- ``DB_PATH``: default DB path (env SHOP_DB_PATH overrides).
- Adapters: ``DbAdapter``, ``SqliteAdapter``, ``PostgresAdapter``.
"""

import os
from pathlib import Path

from .sqldb import SqlDb
from .table import Table
from .column import Column, Integer, String, Float, Boolean, Timestamp, Blob
from .adapters import DbAdapter, SqliteAdapter, PostgresAdapter

# Allow override via environment variable for testing
DB_PATH = Path(os.environ.get("SHOP_DB_PATH", Path(__file__).parent.parent / "shop.db"))

__all__ = [
    "SqlDb",
    "Table",
    "Column",
    "Integer",
    "String",
    "Float",
    "Boolean",
    "Timestamp",
    "Blob",
    "DB_PATH",
    "DbAdapter",
    "SqliteAdapter",
    "PostgresAdapter",
]
