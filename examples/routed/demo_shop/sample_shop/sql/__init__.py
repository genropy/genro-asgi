"""
Source of truth for SQL utilities in the demo shop.

Exports:
- ``SqlDb``: thread-safe DB manager with adapters (see sqldb.py contract).
- ``Table``: smartroute-based table base class with router+plugins.
- ``DB_PATH``: default DB path (env SHOP_DB_PATH overrides).
- Adapters: ``DbAdapter``, ``SqliteAdapter``, ``PostgresAdapter``.
"""

import os
from pathlib import Path

from .sqldb import SqlDb
from .table import Table
from .adapters import DbAdapter, SqliteAdapter, PostgresAdapter

# Allow override via environment variable for testing
DB_PATH = Path(os.environ.get("SHOP_DB_PATH", Path(__file__).parent.parent / "shop.db"))

__all__ = [
    "SqlDb",
    "Table",
    "DB_PATH",
    "DbAdapter",
    "SqliteAdapter",
    "PostgresAdapter",
]
