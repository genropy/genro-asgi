"""SQLite database adapter with schema generation from Column definitions."""

import sqlite3
from typing import Any

from .base import DbAdapter
from ..column import Column


class SqliteAdapter(DbAdapter):
    """SQLite database adapter. Generates schema from Column definitions."""

    def connect(self):
        """Create and return a new SQLite connection."""
        conn = sqlite3.connect(self.connection_info)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def check_structure(self):
        """Generate and execute CREATE TABLE statements from registered tables."""
        cursor = self.cursor()

        for table_name, table_instance in self.db.tables.items():
            sql = self._generate_create_table(table_instance)
            cursor.execute(sql)

        self.commit()

    def _generate_create_table(self, table_instance: Any) -> str:
        """Generate CREATE TABLE SQL from a Table instance's columns."""
        table_name = table_instance.name
        col_defs = []
        fk_defs = []

        for col_name, col in table_instance.columns.items():
            col_sql = self._column_to_sql(col_name, col)
            col_defs.append(col_sql)

            # Collect foreign key constraints only if sql=True
            if col.relation_table and col.relation_sql:
                fk_defs.append(
                    f"FOREIGN KEY ({col_name}) REFERENCES {col.relation_table}({col.relation_pk})"
                )

        all_defs = col_defs + fk_defs
        defs_sql = ",\n            ".join(all_defs)
        return f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
            {defs_sql}
            )
        """

    def _column_to_sql(self, name: str, col: Column) -> str:
        """Convert a Column to SQLite column definition."""
        if col.primary_key and col.autoincrement:
            return f"{name} {col.type_} PRIMARY KEY AUTOINCREMENT"

        if col.primary_key:
            return f"{name} {col.type_} PRIMARY KEY"

        parts = [name, col.type_]

        if not col.nullable:
            parts.append("NOT NULL")

        if col.unique:
            parts.append("UNIQUE")

        if col.default is not None:
            default = col.default
            if isinstance(default, str):
                parts.append(f"DEFAULT '{default}'")
            elif isinstance(default, bool):
                parts.append(f"DEFAULT {1 if default else 0}")
            else:
                parts.append(f"DEFAULT {default}")

        return " ".join(parts)

    def upsert(
        self,
        table: str,
        cursor,
        conflict_column: str,
        **values,
    ) -> int:
        """SQLite upsert using INSERT ... ON CONFLICT DO UPDATE."""
        cols = list(values.keys())
        vals = list(values.values())
        placeholders = ", ".join(["?"] * len(cols))

        # Build SET clause for update (exclude conflict column)
        set_parts = [f"{c} = excluded.{c}" for c in cols if c != conflict_column]

        if set_parts:
            sql = f"""
                INSERT INTO {table} ({", ".join(cols)}) VALUES ({placeholders})
                ON CONFLICT({conflict_column}) DO UPDATE SET {", ".join(set_parts)}
            """
        else:
            # Only conflict column provided - just ignore on conflict
            sql = f"""
                INSERT INTO {table} ({", ".join(cols)}) VALUES ({placeholders})
                ON CONFLICT({conflict_column}) DO NOTHING
            """

        cursor.execute(sql, vals)
        return cursor.lastrowid
