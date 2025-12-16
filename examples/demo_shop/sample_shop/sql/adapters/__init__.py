"""Database adapters for multiple backends."""

from .base import DbAdapter
from .sqlite import SqliteAdapter
from .postgres import PostgresAdapter

# Registry of available adapters
ADAPTERS = {
    "sqlite": SqliteAdapter,
    "postgres": PostgresAdapter,
}

__all__ = [
    "DbAdapter",
    "SqliteAdapter",
    "PostgresAdapter",
    "ADAPTERS",
]
