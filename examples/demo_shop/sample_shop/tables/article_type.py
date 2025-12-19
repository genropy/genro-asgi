"""ArticleType table with Columns definitions."""

from genro_routes import route
from ..sql import Table, Integer, String, FormatParam
from ..responses import IdResponse, RecordResponse, ListResponse, MessageResponse


class ArticleType(Table):
    """Manage article types."""

    schema = None
    name = "article_type"
    name_long = "Article Type"
    name_plural = "Article Types"

    def configure(self):
        c = self.columns
        c.column("id", Integer, primary_key=True, autoincrement=True)
        c.column("name", String, unique=True)
        c.column("description", String, default="")

    @route("table")
    def add(self, name: str, description: str = "") -> IdResponse:
        """Add or update article type."""
        row_id = self.db.upsert(self.name, "name", name=name, description=description)
        self.db.commit()
        return self._success(id=row_id, message=f"ArticleType '{name}' saved")

    @route("table", openapi_method="get")
    def get(self, id: int) -> RecordResponse:
        """Get article type by id."""
        row = self.db.select_one(self.name, where={"id": id})
        if not row:
            return self._error(f"ArticleType with id {id} not found")
        return self._success(record=row)

    @route("table", openapi_method="get")
    def list(self, format: FormatParam = "json") -> ListResponse | str:
        """List all article types."""
        records = self.db.select(self.name)
        return self._apply_format(records, ["id", "name", "description"], format)

    @route("table")
    def remove(self, id: int) -> MessageResponse:
        """Remove article type by id."""
        if not self.db.exists(self.name, where={"id": id}):
            return self._error(f"ArticleType with id {id} not found")
        self.db.delete(self.name, where={"id": id})
        self.db.commit()
        return self._success(message=f"ArticleType id={id} removed")
