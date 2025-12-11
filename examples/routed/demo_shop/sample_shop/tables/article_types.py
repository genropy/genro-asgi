"""ArticleTypes: router-powered manager for article type records."""

from smartroute import route
from ..sql import Table


class ArticleTypes(Table):
    """Manage article types like shoes, clothing, books."""

    _table_name = "article_types"  # Database table name
    _registry_name = "types"  # Registry key for shop.db.table('types')

    @route("types")
    def add(self, name: str, description: str = "", cursor=None, autocommit: bool = False) -> dict:
        """
        Add a new article type.

        Args:
            name: Unique name for the article type
            description: Optional description
            cursor: Database cursor (auto-injected by DbopPlugin)
            autocommit: Auto-commit transaction (handled by DbopPlugin)

        Returns:
            Dictionary with id and confirmation message
        """
        result = self._add(
            columns=["name", "description"],
            values=[name, description],
            unique_check={"name": name},
            cursor=cursor,
        )
        if result["success"]:
            result["message"] = f"Article type '{name}' created with id {result['id']}"
        return result

    @route("types")
    def remove(self, id: int, cursor=None, autocommit: bool = False) -> dict:
        """
        Remove an article type by id.

        Args:
            id: Article type id to remove
            cursor: Database cursor (auto-injected by DbopPlugin)
            autocommit: Auto-commit transaction (handled by DbopPlugin)

        Returns:
            Dictionary with success status
        """
        # Get name before deleting
        cursor.execute("SELECT name FROM article_types WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            return self._error(f"Article type with id {id} not found")

        name = row[0]

        # Check if has articles (business rule - foreign key check)
        cursor.execute("SELECT COUNT(*) FROM articles WHERE article_type_id = ?", (id,))
        count = cursor.fetchone()[0]
        if count > 0:
            return self._error(f"Cannot remove: there are {count} articles of this type")

        # Delete using helper
        result = self._remove(id, cursor)
        if result["success"]:
            result["message"] = f"Article type '{name}' (id={id}) removed"
        return result

    @route("types")
    def list(self, format: str = "json", cursor=None):
        """
        List all article types.

        Args:
            format: Output format (json|markdown|table|html)
            cursor: Database cursor (auto-injected by DbopPlugin)

        Returns:
            Dictionary with list of article types (json) or formatted string
        """
        return self._list(
            columns=["id", "name", "description"],
            format=format,
            order_by="name",
            result_key="types",
            cursor=cursor,
        )

    @route("types")
    def get(self, id: int, cursor=None) -> dict:
        """
        Get a single article type by id.

        Args:
            id: Article type id
            cursor: Database cursor (auto-injected by DbopPlugin)

        Returns:
            Dictionary with article type details
        """
        return self._get(
            id=id, columns=["id", "name", "description"], result_key="type", cursor=cursor
        )
