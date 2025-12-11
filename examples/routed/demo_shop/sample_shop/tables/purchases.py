"""Purchases: router-powered manager for purchase records and statistics."""

from typing import Annotated
from pydantic import Field
from smartroute import route
from ..sql import Table


class Purchases(Table):
    """Manage purchases of articles."""

    _table_name = "purchases"
    _registry_name = "purchases"

    @route("purchases")
    def add(
        self,
        article_id: int,
        quantity: Annotated[int, Field(gt=0, description="Quantity must be greater than zero")],
        cursor=None,
        autocommit: bool = False,
    ) -> dict:
        """
        Register a new purchase.

        Args:
            article_id: Article id to purchase
            quantity: Quantity to purchase (must be positive)
            cursor: Database cursor (auto-injected by DbopPlugin)
            autocommit: Auto-commit transaction (handled by DbopPlugin)

        Returns:
            Dictionary with purchase id and total
        """
        # Check if article exists and get price
        cursor.execute("SELECT code, description, price FROM articles WHERE id = ?", (article_id,))
        article_row = cursor.fetchone()
        if not article_row:
            return {"success": False, "error": f"Article with id {article_id} not found"}

        code = article_row[0]
        description = article_row[1]
        price = article_row[2]
        total = price * quantity

        # Insert purchase
        cursor.execute(
            "INSERT INTO purchases (article_id, quantity) VALUES (?, ?)", (article_id, quantity)
        )

        return {
            "success": True,
            "id": cursor.lastrowid,
            "article": {"id": article_id, "code": code, "description": description, "price": price},
            "quantity": quantity,
            "total": total,
            "message": f"Purchase registered: {quantity}x {code} = ${total:.2f}",
        }

    @route("purchases")
    def remove(self, id: int, cursor=None, autocommit: bool = True) -> dict:
        """
        Remove a purchase by id.

        Args:
            id: Purchase id to remove
            cursor: Database cursor (auto-injected by DbopPlugin)
            autocommit: Auto-commit transaction (handled by DbopPlugin)

        Returns:
            Dictionary with success status
        """
        # Check if exists
        cursor.execute("SELECT article_id, quantity FROM purchases WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "error": f"Purchase with id {id} not found"}

        # Delete
        cursor.execute("DELETE FROM purchases WHERE id = ?", (id,))

        return {"success": True, "message": f"Purchase id={id} removed"}

    @route("purchases")
    def list(self, format: str = "json", article_id: int | None = None, cursor=None):
        """
        List purchases, optionally filtered by article.

        Args:
            format: Output format (json|markdown|table|html)
            article_id: Optional filter by article
            cursor: Database cursor (auto-injected by DbopPlugin)

        Returns:
            Dictionary with list of purchases (json) or formatted string
        """
        if article_id is not None:
            query = """
                SELECT p.id, p.article_id, a.code, a.description,
                       p.quantity, a.price, p.purchase_date
                FROM purchases p
                JOIN articles a ON p.article_id = a.id
                WHERE p.article_id = ?
                ORDER BY p.purchase_date DESC
            """
            cursor.execute(query, (article_id,))
        else:
            query = """
                SELECT p.id, p.article_id, a.code, a.description,
                       p.quantity, a.price, p.purchase_date
                FROM purchases p
                JOIN articles a ON p.article_id = a.id
                ORDER BY p.purchase_date DESC
            """
            cursor.execute(query)

        rows = cursor.fetchall()

        purchases = [
            {
                "id": row[0],
                "article_id": row[1],
                "code": row[2],
                "description": row[3],
                "quantity": row[4],
                "unit_price": row[5],
                "total": row[4] * row[5],
                "purchase_date": row[6],
            }
            for row in rows
        ]

        # Calculate totals
        grand_total = sum(p["total"] for p in purchases)

        # Apply formatting using base class helper
        # Note: grand_total is only included in JSON format via extra_data
        columns = [
            "id",
            "article_id",
            "code",
            "description",
            "quantity",
            "unit_price",
            "total",
            "purchase_date",
        ]
        return self._apply_format(
            purchases, columns, format, result_key="purchases", grand_total=grand_total
        )

    @route("purchases")
    def get(self, id: int, cursor=None) -> dict:
        """
        Get a single purchase by id.

        Args:
            id: Purchase id
            cursor: Database cursor (auto-injected by DbopPlugin)

        Returns:
            Dictionary with purchase details
        """
        query = """
            SELECT p.id, p.article_id, a.code, a.description,
                   p.quantity, a.price, p.purchase_date
            FROM purchases p
            JOIN articles a ON p.article_id = a.id
            WHERE p.id = ?
        """
        cursor.execute(query, (id,))
        row = cursor.fetchone()

        if not row:
            return {"success": False, "error": f"Purchase with id {id} not found"}

        return {
            "success": True,
            "purchase": {
                "id": row[0],
                "article_id": row[1],
                "code": row[2],
                "description": row[3],
                "quantity": row[4],
                "unit_price": row[5],
                "total": row[4] * row[5],
                "purchase_date": row[6],
            },
        }

    @route("purchases")
    def statistics(self, cursor=None) -> dict:
        """
        Get purchase statistics.

        Args:
            cursor: Database cursor (auto-injected by DbopPlugin)

        Returns:
            Dictionary with aggregated statistics
        """
        # Total purchases
        cursor.execute("SELECT COUNT(*) FROM purchases")
        total_purchases = cursor.fetchone()[0]

        # Most purchased articles
        query = """
            SELECT a.code, a.description, SUM(p.quantity) as total_quantity,
                   COUNT(p.id) as purchase_count, SUM(p.quantity * a.price) as total_value
            FROM purchases p
            JOIN articles a ON p.article_id = a.id
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

        # Total revenue
        cursor.execute(
            "SELECT SUM(p.quantity * a.price) FROM purchases p JOIN articles a ON p.article_id = a.id"
        )
        total_revenue = cursor.fetchone()[0] or 0

        return {
            "success": True,
            "total_purchases": total_purchases,
            "total_revenue": total_revenue,
            "top_articles": top_articles,
        }
