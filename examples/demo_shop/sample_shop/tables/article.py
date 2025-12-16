"""Article table with Columns definitions and custom methods."""

from typing import Annotated
from pydantic import Field
from genro_routes import route
from ..sql import Table, Integer, String, Float
from ..responses import IdResponse, RecordResponse, ListResponse, MessageResponse


class Article(Table):
    """Manage shop articles. CRUD + custom methods."""

    schema = None
    name = "article"
    name_long = "Article"
    name_plural = "Articles"

    def configure(self):
        c = self.columns
        c.column("id", Integer, primary_key=True, autoincrement=True)
        c.column("article_type_id", Integer).relation(table="article_type")
        c.column("code", String, unique=True)
        c.column("description", String)
        c.column("price", Float)

    @route("table")
    def add(
        self,
        article_type_id: int,
        code: str,
        description: str,
        price: float,
    ) -> IdResponse:
        """Add or update article."""
        row_id = self.db.upsert(
            self.name, "code",
            article_type_id=article_type_id,
            code=code,
            description=description,
            price=price,
        )
        self.db.commit()
        return self._success(id=row_id, message=f"Article '{code}' saved")

    @route("table", openapi_method="get")
    def get(self, id: int) -> RecordResponse:
        """Get article by id."""
        row = self.db.select_one(self.name, where={"id": id})
        if not row:
            return self._error(f"Article with id {id} not found")
        return self._success(record=row)

    @route("table", openapi_method="get")
    def list(self, format: str = "json") -> ListResponse | str:
        """List all articles."""
        records = self.db.select(self.name)
        cols = ["id", "article_type_id", "code", "description", "price"]
        return self._apply_format(records, cols, format)

    @route("table")
    def remove(self, id: int) -> MessageResponse:
        """Remove article by id."""
        if not self.db.exists(self.name, where={"id": id}):
            return self._error(f"Article with id {id} not found")
        self.db.delete(self.name, where={"id": id})
        self.db.commit()
        return self._success(message=f"Article id={id} removed")

    @route("table")
    def update_price(
        self,
        id: int,
        new_price: Annotated[float, Field(gt=0, description="Price must be greater than zero")],
    ) -> MessageResponse:
        """Update article price."""
        row = self.db.select_one(self.name, columns=["code", "price"], where={"id": id})
        if not row:
            return self._error(f"Article with id {id} not found")

        self.db.update(self.name, values={"price": new_price}, where={"id": id})
        self.db.commit()
        return self._success(
            message=f"Article '{row['code']}' price updated from {row['price']} to {new_price}"
        )
