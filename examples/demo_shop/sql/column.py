"""Column and Columns definitions for table schema."""

from __future__ import annotations
from typing import Any

# SQL Types
Integer = "INTEGER"
String = "TEXT"
Float = "REAL"
Boolean = "INTEGER"
Timestamp = "TIMESTAMP"
Blob = "BLOB"


class Column:
    """Column definition with SQL type, constraints, and optional relation."""

    def __init__(
        self,
        name: str,
        type_: str,
        *,
        primary_key: bool = False,
        autoincrement: bool = False,
        unique: bool = False,
        nullable: bool = True,
        default: Any = None,
    ):
        self.name = name
        self.type_ = type_
        self.primary_key = primary_key
        self.autoincrement = autoincrement
        self.unique = unique
        self.nullable = nullable
        self.default = default
        # Relation info (set via relation() method)
        self.relation_table: str | None = None
        self.relation_pk: str | None = None
        self.relation_sql: bool = False

    def relation(self, table: str, pk: str = "id", sql: bool = False) -> Column:
        """Define a foreign key relation to another table.

        Args:
            table: Target table name
            pk: Primary key column in target table (default: "id")
            sql: If True, generate SQL FOREIGN KEY constraint
        """
        self.relation_table = table
        self.relation_pk = pk
        self.relation_sql = sql
        return self


class Columns:
    """Container for table columns."""

    def __init__(self):
        self._columns: dict[str, Column] = {}

    def column(
        self,
        name: str,
        type_: str,
        *,
        primary_key: bool = False,
        autoincrement: bool = False,
        unique: bool = False,
        nullable: bool = True,
        default: Any = None,
    ) -> Column:
        """Add a column definition. Returns the Column for fluent relation()."""
        col = Column(
            name=name,
            type_=type_,
            primary_key=primary_key,
            autoincrement=autoincrement,
            unique=unique,
            nullable=nullable,
            default=default,
        )
        self._columns[name] = col
        return col

    def items(self):
        """Return column name-definition pairs."""
        return self._columns.items()

    def keys(self):
        """Return column names."""
        return self._columns.keys()

    def get(self, name: str) -> Column | None:
        """Get column by name."""
        return self._columns.get(name)

    def __iter__(self):
        return iter(self._columns)

    def __len__(self):
        return len(self._columns)
