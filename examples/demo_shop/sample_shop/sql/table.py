"""Table base class with Columns-based schema."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from genro_routes import Router, RoutedClass, route
from .column import Columns

# Type annotation for format parameter - enum loaded from endpoint at runtime
FormatParam = Annotated[str, Field(json_schema_extra={"x-enum-endpoint": "list_formats"})]


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

    @route("table", openapi_method="get")
    def list_formats(self) -> list[str]:
        """Ritorna i formati disponibili dai metodi _format_*."""
        return [name[8:] for name in dir(self) if name.startswith("_format_")]

    def _apply_format(
        self,
        records: list[dict[str, Any]],
        columns: list[str],
        format: str = "json",
    ) -> dict[str, Any] | str:
        # Set content_type based on format via ContextVar
        content_type_map = {
            "html": "text/html",
            "csv": "text/csv",
            "markdown": "text/plain",
            "table": "text/plain",
        }
        if format in content_type_map:
            response = self.db.app.response
            if response:
                response.content_type = content_type_map[format]

        formatter = getattr(self, f"_format_{format}", None)
        if formatter:
            return formatter(records, columns)
        return self._format_json(records, columns)

    def _format_json(self, records: list[dict[str, Any]], columns: list[str]) -> dict[str, Any]:
        return self._success(count=len(records), records=records)

    def _format_csv(self, records: list[dict[str, Any]], columns: list[str]) -> str:
        if not records:
            return ""
        header = ",".join(columns)
        rows = [",".join(str(r.get(c, "")) for c in columns) for r in records]
        return "\n".join([header] + rows)

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


__all__ = ["Table", "FormatParam"]
