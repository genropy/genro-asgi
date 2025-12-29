"""Base adapter class for database backends."""

from abc import ABC, abstractmethod
from typing import Any


class DbAdapter(ABC):
    """Abstract base class for database adapters with CRUD helpers."""

    placeholder = "?"  # Override in subclass (e.g., "%s" for PostgreSQL)

    def __init__(self, connection_info: str, db):
        self.connection_info = connection_info
        self.db = db

    @abstractmethod
    def connect(self):
        """Create and return a new database connection."""
        pass

    def cursor(self):
        """Get a cursor from the current thread's connection."""
        return self.db.connection.cursor()

    def commit(self):
        """Commit current thread's transaction."""
        self.db.connection.commit()

    def rollback(self):
        """Rollback current thread's transaction."""
        self.db.connection.rollback()

    @abstractmethod
    def check_structure(self):
        """Check and create database schema if needed."""
        pass

    # --- CRUD helpers ---

    def insert(self, table: str, cursor: Any, **values) -> int:
        """Insert a row, return lastrowid."""
        cols = list(values.keys())
        vals = list(values.values())
        placeholders = ", ".join([self.placeholder] * len(cols))
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        cursor.execute(sql, vals)
        return cursor.lastrowid

    def select(
        self,
        table: str,
        cursor: Any,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Select rows, return list of dicts."""
        cols_sql = ", ".join(columns) if columns else "*"
        sql = f"SELECT {cols_sql} FROM {table}"
        params = []

        if where:
            conditions = [f"{k} = {self.placeholder}" for k in where.keys()]
            sql += " WHERE " + " AND ".join(conditions)
            params = list(where.values())

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        # Convert to list of dicts
        if columns:
            return [{col: row[i] for i, col in enumerate(columns)} for row in rows]
        # If columns not specified, use cursor.description
        col_names = [desc[0] for desc in cursor.description]
        return [{col: row[i] for i, col in enumerate(col_names)} for row in rows]

    def select_one(
        self,
        table: str,
        cursor: Any,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Select single row, return dict or None."""
        results = self.select(table, cursor, columns, where)
        return results[0] if results else None

    def update(
        self,
        table: str,
        cursor: Any,
        values: dict[str, Any],
        where: dict[str, Any],
    ) -> int:
        """Update rows, return rowcount."""
        set_parts = [f"{k} = {self.placeholder}" for k in values.keys()]
        where_parts = [f"{k} = {self.placeholder}" for k in where.keys()]

        sql = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"
        params = list(values.values()) + list(where.values())

        cursor.execute(sql, params)
        return cursor.rowcount

    def delete(self, table: str, cursor: Any, where: dict[str, Any]) -> int:
        """Delete rows, return rowcount."""
        where_parts = [f"{k} = {self.placeholder}" for k in where.keys()]
        sql = f"DELETE FROM {table} WHERE {' AND '.join(where_parts)}"
        params = list(where.values())

        cursor.execute(sql, params)
        return cursor.rowcount

    def exists(self, table: str, cursor: Any, where: dict[str, Any]) -> bool:
        """Check if row exists."""
        return self.select_one(table, cursor, columns=["1"], where=where) is not None

    def upsert(
        self,
        table: str,
        cursor: Any,
        conflict_column: str,
        **values,
    ) -> int:
        """Insert or update row based on conflict column. Return lastrowid."""
        raise NotImplementedError("Subclasses must implement upsert()")
