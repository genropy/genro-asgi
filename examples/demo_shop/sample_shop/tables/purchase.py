"""Purchase table with Columns definitions and custom methods."""

from genro_routes import route
from ..sql import Table, Integer, Timestamp
from ..responses import IdResponse, RecordResponse, ListResponse, MessageResponse, StatsResponse


class Purchase(Table):
    """Manage purchases. CRUD + statistics."""

    schema = None
    name = "purchase"
    name_long = "Purchase"
    name_plural = "Purchases"

    def configure(self):
        c = self.columns
        c.column("id", Integer, primary_key=True, autoincrement=True)
        c.column("article_id", Integer).relation(table="article")
        c.column("quantity", Integer)
        c.column("purchase_date", Timestamp)

    @route("table")
    def add(self, article_id: int, quantity: int) -> IdResponse:
        """Add a new purchase."""
        row_id = self.db.insert(
            self.name,
            article_id=article_id,
            quantity=quantity,
            purchase_date=self.db.now(),
        )
        self.db.commit()
        return self._success(id=row_id, message=f"Purchase created for article {article_id}")

    @route("table", openapi_method="get")
    def get(self, id: int) -> RecordResponse:
        """Get purchase by id."""
        row = self.db.select_one(self.name, where={"id": id})
        if not row:
            return self._error(f"Purchase with id {id} not found")
        return self._success(record=row)

    @route("table", openapi_method="get")
    def list(self, format: str = "json") -> ListResponse | str:
        """List all purchases."""
        records = self.db.select(self.name)
        cols = ["id", "article_id", "quantity", "purchase_date"]
        return self._apply_format(records, cols, format)

    @route("table")
    def remove(self, id: int) -> MessageResponse:
        """Remove purchase by id."""
        if not self.db.exists(self.name, where={"id": id}):
            return self._error(f"Purchase with id {id} not found")
        self.db.delete(self.name, where={"id": id})
        self.db.commit()
        return self._success(message=f"Purchase id={id} removed")

    @route("table")
    def statistics(self) -> StatsResponse:
        """Get purchase statistics."""
        cursor = self.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM purchase")
        total_purchases = cursor.fetchone()[0]

        query = """
            SELECT a.code, a.description, SUM(p.quantity) as total_quantity,
                   COUNT(p.id) as purchase_count, SUM(p.quantity * a.price) as total_value
            FROM purchase p
            JOIN article a ON p.article_id = a.id
            GROUP BY a.id, a.code, a.description
            ORDER BY total_quantity DESC
            LIMIT 10
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        top_articles = [
            {
                "code": row[0],
                "description": row[1],
                "total_quantity": row[2],
                "purchase_count": row[3],
                "total_value": row[4],
            }
            for row in rows
        ]

        cursor.execute(
            "SELECT SUM(p.quantity * a.price) FROM purchase p JOIN article a ON p.article_id = a.id"
        )
        total_revenue = cursor.fetchone()[0] or 0

        return self._success(
            total_purchases=total_purchases,
            total_revenue=total_revenue,
            top_articles=top_articles,
        )
