"""Articles: router-powered manager for products with validation and CRUD helpers."""

from typing import Annotated
from pydantic import Field
from smartroute import route
from ..sql import Table


class Articles(Table):
    """Manage shop articles with code, description, price."""

    _table_name = "articles"
    _registry_name = "articles"

    @route("articles")
    def add(
        self,
        article_type_id: int,
        code: str,
        description: str,
        price: Annotated[float, Field(gt=0, description="Price must be greater than zero")],
        cursor=None,
        autocommit: bool = False,
    ) -> dict:
        """
        Add a new article.

        Args:
            article_type_id: Reference to article type (foreign key)
            code: Unique article code
            description: Article description
            price: Article price (must be positive)
            cursor: Database cursor (auto-injected by DbopPlugin)
            autocommit: Auto-commit transaction (handled by DbopPlugin)

        Returns:
            Dictionary with id and confirmation message
        """
        # Check if article_type exists
        cursor.execute("SELECT name FROM article_types WHERE id = ?", (article_type_id,))
        type_row = cursor.fetchone()
        if not type_row:
            return {"success": False, "error": f"Article type with id {article_type_id} not found"}

        # Check if code already exists
        cursor.execute("SELECT id FROM articles WHERE code = ?", (code,))
        existing = cursor.fetchone()
        if existing:
            return {
                "success": False,
                "error": f"Article with code '{code}' already exists with id {existing[0]}",
            }

        # Insert
        cursor.execute(
            """INSERT INTO articles (article_type_id, code, description, price)
               VALUES (?, ?, ?, ?)""",
            (article_type_id, code, description, price),
        )

        return {
            "success": True,
            "id": cursor.lastrowid,
            "message": f"Article '{code}' created with id {cursor.lastrowid}",
        }

    @route("articles")
    def remove(self, id: int, cursor=None, autocommit: bool = True) -> dict:
        """
        Remove an article by id.

        Args:
            id: Article id to remove
            cursor: Database cursor (auto-injected by DbopPlugin)
            autocommit: Auto-commit transaction (handled by DbopPlugin)

        Returns:
            Dictionary with success status
        """
        # Check if exists
        cursor.execute("SELECT code FROM articles WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "error": f"Article with id {id} not found"}

        code = row[0]

        # Check if has purchases
        cursor.execute("SELECT COUNT(*) FROM purchases WHERE article_id = ?", (id,))
        count = cursor.fetchone()[0]
        if count > 0:
            return {
                "success": False,
                "error": f"Cannot remove: there are {count} purchases for this article",
            }

        # Delete
        cursor.execute("DELETE FROM articles WHERE id = ?", (id,))

        return {"success": True, "message": f"Article '{code}' (id={id}) removed"}

    @route("articles")
    def list(self, format: str = "json", article_type_id: int | None = None, cursor=None):
        """
        List articles, optionally filtered by type.

        Args:
            format: Output format (json|markdown|table|html)
            article_type_id: Optional filter by article type
            cursor: Database cursor (auto-injected by DbopPlugin)

        Returns:
            Dictionary with list of articles (json) or formatted string
        """
        if article_type_id is not None:
            query = """
                SELECT a.id, a.code, a.description, a.price, t.name as type
                FROM articles a
                JOIN article_types t ON a.article_type_id = t.id
                WHERE a.article_type_id = ?
                ORDER BY a.code
            """
            cursor.execute(query, (article_type_id,))
        else:
            query = """
                SELECT a.id, a.code, a.description, a.price, t.name as type
                FROM articles a
                JOIN article_types t ON a.article_type_id = t.id
                ORDER BY a.code
            """
            cursor.execute(query)

        rows = cursor.fetchall()

        articles = [
            {"id": row[0], "code": row[1], "description": row[2], "price": row[3], "type": row[4]}
            for row in rows
        ]

        # Apply formatting using base class helper
        columns = ["id", "code", "description", "price", "type"]
        return self._apply_format(articles, columns, format, result_key="articles")

    @route("articles")
    def get(self, id: int, cursor=None) -> dict:
        """
        Get a single article by id.

        Args:
            id: Article id
            cursor: Database cursor (auto-injected by DbopPlugin)

        Returns:
            Dictionary with article details
        """
        query = """
            SELECT a.id, a.code, a.description, a.price,
                   a.article_type_id, t.name as type
            FROM articles a
            JOIN article_types t ON a.article_type_id = t.id
            WHERE a.id = ?
        """
        cursor.execute(query, (id,))
        row = cursor.fetchone()

        if not row:
            return {"success": False, "error": f"Article with id {id} not found"}

        return {
            "success": True,
            "article": {
                "id": row[0],
                "code": row[1],
                "description": row[2],
                "price": row[3],
                "article_type_id": row[4],
                "type": row[5],
            },
        }

    @route("articles")
    def update_price(
        self,
        id: int,
        new_price: Annotated[float, Field(gt=0, description="Price must be greater than zero")],
        cursor=None,
        autocommit: bool = False,
    ) -> dict:
        """
        Update article price.

        Args:
            id: Article id
            new_price: New price (must be positive)
            cursor: Database cursor (auto-injected by DbopPlugin)
            autocommit: Auto-commit transaction (handled by DbopPlugin)

        Returns:
            Dictionary with success status
        """
        # Check if exists
        cursor.execute("SELECT code, price FROM articles WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            return {"success": False, "error": f"Article with id {id} not found"}

        code = row[0]
        old_price = row[1]

        # Update
        cursor.execute("UPDATE articles SET price = ? WHERE id = ?", (new_price, id))

        return {
            "success": True,
            "message": f"Article '{code}' price updated from {old_price} to {new_price}",
        }
