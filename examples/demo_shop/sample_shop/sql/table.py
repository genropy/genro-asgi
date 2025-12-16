"""Table base class with Columns-based schema."""

from __future__ import annotations

from typing import Any

from genro_routes import Router, RoutedClass
from .column import Columns


class Table(RoutedClass):
    """Base class for table managers. Subclasses define columns via configure() hook.

    Naming convention:
        schema: Optional schema name (None for SQLite, used by PostgreSQL)
        name: Singular table name (e.g., 'article')
        name_long: Display name (e.g., 'Article')
        name_plural: Plural form (e.g., 'Articles')

    Subclasses override configure() to define columns and relations.
    """

    schema: str | None = None
    name: str
    name_long: str
    name_plural: str

    def __init__(self, db: Any) -> None:
        self.db = db
        if not hasattr(self, "name") or not self.name:
            raise ValueError(f"{type(self).__name__} must define name")

        self.columns = Columns()
        self.configure()

        self.api = (
            Router(self, name="table")
            .plug("logging")
        )

    def configure(self) -> None:
        """Override to define columns and relations."""
        pass

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke a handler with the plugin pipeline active."""
        return self.api.call(method, *args, **kwargs)

    # --- Response builders ---

    def _success(self, **kwargs: Any) -> dict[str, Any]:
        return {"success": True, **kwargs}

    def _error(self, message: str) -> dict[str, Any]:
        return {"success": False, "error": message}

    # --- Formatting ---

    def _apply_format(
        self,
        records: list[dict[str, Any]],
        columns: list[str],
        format: str = "json",
    ) -> dict[str, Any] | str:
        if format == "json":
            return self._success(count=len(records), records=records)
        elif format == "markdown":
            return self._format_markdown(records, columns)
        elif format == "table":
            return self._format_table(records, columns)
        elif format == "html":
            return self._format_html(records, columns)
        return self._success(count=len(records), records=records)

    def _format_markdown(self, records: list[dict[str, Any]], columns: list[str]) -> str:
        if not records:
            return "No records found."
        header = "| " + " | ".join(columns) + " |"
        separator = "|" + "|".join([" --- "] * len(columns)) + "|"
        rows = ["| " + " | ".join(str(r.get(c, "")) for c in columns) + " |" for r in records]
        return "\n".join([header, separator] + rows)

    def _format_table(self, records: list[dict[str, Any]], columns: list[str]) -> str:
        if not records:
            return "No records found."
        widths = {c: max(len(c), max((len(str(r.get(c, ""))) for r in records), default=0)) for c in columns}
        row_fmt = "| " + " | ".join(f"{{:<{widths[c]}}}" for c in columns) + " |"
        sep = "+" + "+".join(["-" * (widths[c] + 2) for c in columns]) + "+"
        lines = [sep, row_fmt.format(*columns), sep]
        lines.extend(row_fmt.format(*[str(r.get(c, "")) for c in columns]) for r in records)
        lines.append(sep)
        return "\n".join(lines)

    def _format_html(self, records: list[dict[str, Any]], columns: list[str]) -> str:
        if not records:
            return "<p>No records found.</p>"
        rows = "\n".join(
            "    <tr>" + "".join(f"<td>{r.get(c, '')}</td>" for c in columns) + "</tr>"
            for r in records
        )
        header = "    <tr>" + "".join(f"<th>{c}</th>" for c in columns) + "</tr>"
        return f"<table>\n  <thead>\n{header}\n  </thead>\n  <tbody>\n{rows}\n  </tbody>\n</table>"


__all__ = ["Table"]
