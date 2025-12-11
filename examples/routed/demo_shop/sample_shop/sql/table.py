"""
Source of truth for table manager infrastructure built on smartroute.

Recreate from this contract if the code disappears:

- Module exports: Router-backed ``Table`` base class, ``PydanticExtrasPlugin``
  (registered globally as plugin ``"pydantic_extras"``).

- PydanticExtrasPlugin
    * Extends smartroute's PydanticPlugin but resolves type hints with
      ``include_extras=True`` so ``Annotated[Field(...)]`` constraints are kept.
    * On registration (``on_decore``), builds a pydantic model from function
      annotations (excluding return), respecting defaults and marking others as
      required. Stores metadata in ``entry.metadata["pydantic"]`` with keys
      ``enabled``, ``model``, ``hints``, ``signature``. Disabled when hints
      resolution fails or no hints remain.
    * Registered via ``Router.register_plugin("pydantic_extras", ...)``.

- Table (subclasses must define ``_table_name`` and route methods with @route):
    * Attributes set in __init__(db):
        - ``db``: database manager passed in.
        - ``_registry_name``/``_router_name``: optional overrides for router
          name; fallback to ``_table_name``. Empty names raise ValueError.
        - ``api``: a Router instance with plugin chain
          ``logging -> dbop -> pydantic_extras``.
    * Helper ``call(method, *args, **kwargs)`` invokes ``api.call`` so the
      plugin pipeline is always applied.
    * Base helpers provided:
        - response builders ``_success``/``_error``;
        - guards ``_check_exists``/``_check_unique``/``_check_count``;
        - generic CRUD helpers ``_add``, ``_remove``, ``_get``, ``_list`` plus
          formatters (markdown/table/html) and ``_apply_format``.
    * Subclasses route business methods with ``@route(<router_name>)`` and use
      base helpers; they do not need to manage cursors/transactions explicitly
      because the dbop plugin injects ``cursor`` and manages commit/rollback.

No hidden dependencies beyond smartroute, pydantic, and the database manager
interface (cursor/commit/rollback).
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

from pydantic import create_model
from smartroute import Router, RoutedClass
from smartroute.plugins.pydantic import PydanticPlugin


class PydanticExtrasPlugin(PydanticPlugin):
    """Pydantic plugin variant that keeps Annotated/Field metadata (include_extras=True)."""

    def on_decore(self, route, func, entry):  # type: ignore[override]
        try:
            hints = get_type_hints(func, include_extras=True)
        except Exception:
            entry.metadata["pydantic"] = {"enabled": False}
            return

        hints.pop("return", None)
        if not hints:
            entry.metadata["pydantic"] = {"enabled": False}
            return

        sig = inspect.signature(func)
        fields = {}
        for param_name, hint in hints.items():
            param = sig.parameters.get(param_name)
            if param is None:
                fields[param_name] = (hint, ...)
            elif param.default is inspect.Parameter.empty:
                fields[param_name] = (hint, ...)
            else:
                fields[param_name] = (hint, param.default)

        validation_model = create_model(f"{func.__name__}_Model", **fields)  # type: ignore

        entry.metadata["pydantic"] = {
            "enabled": True,
            "model": validation_model,
            "hints": hints,
            "signature": sig,
        }


Router.register_plugin("pydantic_extras", PydanticExtrasPlugin)


class Table(RoutedClass):
    """
    Base class for table managers.

    Provides common functionality for all table classes:
    - Standard __init__ that stores db reference
    - Response builders (_success, _error)
    - Check helpers (_check_exists, _check_unique, _check_count)
    - Generic CRUD operations (_add, _remove, _get, _list)
    - Router ``api`` with plugin chain (logging, dbop, pydantic_extras)
      to be invoked via ``table.call("method", ...)``

    Subclasses must define:
    - _table_name: The database table name
    - Route methods with @route(<router_name>) matching _router_name/_table_name
    """

    _table_name = None  # Subclasses must override

    _registry_name = None  # Optional custom registry key (e.g., "types")
    _router_name = None  # Optional router name (defaults to _registry_name/_table_name)

    def __init__(self, db):
        """
        Initialize table manager.

        Args:
            db: SqlDb instance for database access
        """
        self.db = db
        router_name = self._router_name or self._registry_name or self._table_name
        if not router_name:
            raise ValueError(f"{type(self).__name__} must define _table_name")

        # Router with the standard plugin chain (logging -> dbop -> pydantic)
        self.api = (
            Router(self, name=router_name).plug("logging").plug("dbop").plug("pydantic_extras")
        )

    def call(self, method: str, *args, **kwargs):
        """Invoke a handler with the plugin pipeline active."""
        return self.api.call(method, *args, **kwargs)

    # Response builders
    def _success(self, **kwargs):
        """Build success response dictionary."""
        return {"success": True, **kwargs}

    def _error(self, message):
        """Build error response dictionary."""
        return {"success": False, "error": message}

    # Check helpers
    def _check_exists(self, id, cursor=None):
        """
        Check if a record exists by id.

        Args:
            id: Record id to check
            cursor: Database cursor

        Returns:
            True if record exists, False otherwise
        """
        cursor.execute(f"SELECT id FROM {self._table_name} WHERE id = ?", (id,))
        return cursor.fetchone() is not None

    def _check_unique(self, column, value, cursor=None):
        """
        Check if a value is unique for a column.

        Args:
            column: Column name to check
            value: Value to check for uniqueness
            cursor: Database cursor

        Returns:
            True if value is unique (not found), False if already exists
        """
        cursor.execute(f"SELECT id FROM {self._table_name} WHERE {column} = ?", (value,))
        return cursor.fetchone() is None

    def _check_count(self, where=None, params=None, cursor=None):
        """
        Count records with optional filter.

        Args:
            where: Optional WHERE clause (without WHERE keyword)
            params: Optional tuple of parameters for WHERE clause
            cursor: Database cursor

        Returns:
            Number of matching records
        """
        query = f"SELECT COUNT(*) FROM {self._table_name}"

        if where:
            query += f" WHERE {where}"

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        return cursor.fetchone()[0]

    # Generic CRUD operations
    def _add(self, columns, values, unique_check=None, message=None, cursor=None):
        """
        Generic insert operation.

        Args:
            columns: List of column names
            values: List of values (same order as columns)
            unique_check: Dict of {column: value} to check for uniqueness
            message: Optional custom success message
            cursor: Database cursor

        Returns:
            Success dict with id, or error dict
        """
        # Check unique constraints using helper
        if unique_check:
            for col, val in unique_check.items():
                if not self._check_unique(col, val, cursor):
                    return self._error(f"{col}='{val}' already exists")

        # Insert
        placeholders = ",".join(["?"] * len(values))
        cols = ",".join(columns)
        cursor.execute(f"INSERT INTO {self._table_name} ({cols}) VALUES ({placeholders})", values)

        result_id = cursor.lastrowid
        if message is None:
            message = f"Record created with id {result_id}"

        return self._success(id=result_id, message=message)

    def _remove(self, id, cursor=None):
        """
        Generic delete operation.

        Args:
            id: Record id to delete
            cursor: Database cursor

        Returns:
            Success dict with message, or error dict
        """
        # Check if exists using helper
        if not self._check_exists(id, cursor):
            return self._error(f"Record with id {id} not found")

        # Delete
        cursor.execute(f"DELETE FROM {self._table_name} WHERE id = ?", (id,))

        return self._success(message=f"Record id={id} removed")

    def _get(self, id, columns, cursor=None, result_key="record"):
        """
        Generic get by id operation.

        Args:
            id: Record id to fetch
            columns: List of column names to select
            cursor: Database cursor
            result_key: Key name for the result in response dict

        Returns:
            Success dict with record data, or error dict
        """
        cols = ",".join(columns)
        cursor.execute(f"SELECT {cols} FROM {self._table_name} WHERE id = ?", (id,))
        row = cursor.fetchone()

        if not row:
            return self._error(f"Record with id {id} not found")

        # Build result dict
        record = {col: row[i] for i, col in enumerate(columns)}

        return self._success(**{result_key: record})

    def _list(
        self,
        columns,
        format="json",
        cursor=None,
        where=None,
        params=None,
        order_by=None,
        result_key="records",
    ):
        """
        Generic list operation.

        Args:
            columns: List of column names to select
            format: Output format (json|markdown|table|html)
            cursor: Database cursor
            where: Optional WHERE clause (without WHERE keyword)
            params: Optional tuple of parameters for WHERE clause
            order_by: Optional ORDER BY clause (without ORDER BY keyword)
            result_key: Key name for the results list in response dict

        Returns:
            Success dict with count and records list (format='json')
            or formatted string (other formats)
        """
        cols = ",".join(columns)
        query = f"SELECT {cols} FROM {self._table_name}"

        if where:
            query += f" WHERE {where}"

        if order_by:
            query += f" ORDER BY {order_by}"

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        rows = cursor.fetchall()

        # Build results list
        records = [{col: row[i] for i, col in enumerate(columns)} for row in rows]

        # Apply formatting
        return self._apply_format(records, columns, format, result_key)

    def _apply_format(self, records, columns, format="json", result_key="records", **extra_data):
        """
        Apply formatting to a list of records.

        This helper can be used by both _list() and custom list methods
        that prepare their own data.

        Args:
            records: List of record dictionaries
            columns: List of column names (for table headers)
            format: Output format (json|markdown|table|html)
            result_key: Key name for the results list in JSON response
            **extra_data: Additional data to include in JSON response (e.g., grand_total)

        Returns:
            Success dict with data (format='json') or formatted string (other formats)
        """
        if format == "json":
            return self._success(count=len(records), **{result_key: records}, **extra_data)
        elif format == "markdown":
            return self._format_markdown(records, columns)
        elif format == "table":
            return self._format_table(records, columns)
        elif format == "html":
            return self._format_html(records, columns)
        else:
            # Unknown format, default to json
            return self._success(count=len(records), **{result_key: records}, **extra_data)

    # Formatters
    def _format_markdown(self, records, columns):
        """
        Format records as markdown table.

        Args:
            records: List of record dictionaries
            columns: List of column names

        Returns:
            String with markdown table
        """
        if not records:
            return "No records found."

        # Header
        header = "| " + " | ".join(columns) + " |"
        separator = "|" + "|".join([" --- "] * len(columns)) + "|"

        # Rows
        rows = []
        for record in records:
            values = [str(record.get(col, "")) for col in columns]
            row = "| " + " | ".join(values) + " |"
            rows.append(row)

        return "\n".join([header, separator] + rows)

    def _format_table(self, records, columns):
        """
        Format records as ASCII table.

        Args:
            records: List of record dictionaries
            columns: List of column names

        Returns:
            String with ASCII art table
        """
        if not records:
            return "No records found."

        # Calculate column widths
        widths = {col: len(col) for col in columns}
        for record in records:
            for col in columns:
                value_len = len(str(record.get(col, "")))
                if value_len > widths[col]:
                    widths[col] = value_len

        # Build format string
        row_format = "| " + " | ".join(f"{{:<{widths[col]}}}" for col in columns) + " |"
        separator = "+" + "+".join(["-" * (widths[col] + 2) for col in columns]) + "+"

        # Header
        lines = [separator]
        lines.append(row_format.format(*columns))
        lines.append(separator)

        # Rows
        for record in records:
            values = [str(record.get(col, "")) for col in columns]
            lines.append(row_format.format(*values))

        lines.append(separator)
        return "\n".join(lines)

    def _format_html(self, records, columns):
        """
        Format records as HTML table.

        Args:
            records: List of record dictionaries
            columns: List of column names

        Returns:
            String with HTML table
        """
        if not records:
            return "<p>No records found.</p>"

        # Header
        lines = ["<table>"]
        lines.append("  <thead>")
        lines.append("    <tr>")
        for col in columns:
            lines.append(f"      <th>{col}</th>")
        lines.append("    </tr>")
        lines.append("  </thead>")

        # Body
        lines.append("  <tbody>")
        for record in records:
            lines.append("    <tr>")
            for col in columns:
                value = record.get(col, "")
                lines.append(f"      <td>{value}</td>")
            lines.append("    </tr>")
        lines.append("  </tbody>")
        lines.append("</table>")

        return "\n".join(lines)

    @classmethod
    @classmethod
    def create_switcher(cls, name):  # pragma: no cover - legacy shim
        """Legacy alias kept to avoid AttributeError in old imports."""
        raise RuntimeError(
            "smartswitch has been replaced by smartroute; use Table.api/dbop instead."
        )
