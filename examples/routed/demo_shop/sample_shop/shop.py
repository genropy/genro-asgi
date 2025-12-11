"""
Source of truth for the Shop aggregate used in the demo shop.

If this file were wiped, rebuild it from this description:

- Purpose: orchestrate the database manager and register table managers
  (ArticleTypes, Articles, Purchases) for use both in-process and via
  smartroute/smartpublisher exposure.

- __init__(connection_string):
    * Builds ``self.db = SqlDb(connection_string, self)``.
    * Declares ``self.tables = [ArticleTypes, Articles, Purchases]``.
    * Registers each table with ``self.db.add_table(table_class)``; registration
      uses the class' ``_registry_name``/_table_name for lookup.
    * Calls ``self.db.adapter.checkStructure()`` to create/verify schema.

- populateDb():
    * Seeds the database with 4 article types, 20 articles (5 per type) and
      120 random purchases.
    * Uses table routers (``self.db.table("<name>").call(...)``) with
      ``autocommit=False`` then commits once at the end via ``self.db.commit()``.
    * Returns ``{"success": True, "types": <int>, "articles": <int>, "purchases": <int>}``.

- Script usage: running the module directly demonstrates independent Shop
  instances pointing to different SQLite DBs (``Shop("sqlite:shop1.db")`` etc.).

Notes:
- Shop itself is unaware of smartpublisher; publishing is done in
  ``published_shop/main.py`` by mounting the table routers.
- All table methods should be invoked via their router ``call`` helper so the
  dbop/pydantic plugins are applied (cursor injection, validation, commit).
"""

from .sql import SqlDb
from .tables import ArticleTypes, Articles, Purchases


class Shop:
    """
    Shop management class - aggregates database and table managers.

    This is a NORMAL Python class - no smpub required!
    You can instantiate and use it directly:

    ```python
    shop = Shop('sqlite:shop.db')

    # Access tables via shop.db.table(name)
    result = shop.db.table('types').add("electronics", "Electronic devices")

    # See SqlDb documentation for transaction management examples
    ```

    The Shop class:
    - Creates and configures the SqlDb database manager
    - Registers all table classes (ArticleTypes, Articles, Purchases)
    - Initializes the database schema
    - Provides access to tables via shop.db.table(name)

    All database operations and transaction management are handled by SqlDb.
    See SqlDb documentation for details on transactions, thread-safety, etc.

    Optionally, you can publish it with smpub to expose via CLI/HTTP.
    See main.py for publishing example.
    """

    def __init__(self, connection_string):
        """
        Initialize shop with database and table managers.

        Args:
            connection_string: Path to database file
        """
        # Create database manager - pass self as app
        self.db = SqlDb(connection_string, self)

        # declares tables
        self.tables = [ArticleTypes, Articles, Purchases]

        # Register table classes
        for table in self.tables:
            self.db.add_table(table)

        # Check/create schema (delegated to adapter)
        self.db.adapter.checkStructure()

    def populateDb(self):
        """
        Populate database with sample data.

        Creates:
        - 4 article types
        - 20 articles
        - 120 purchases

        Returns:
            Dictionary with counts of created records
        """
        import random

        # Article types
        types_data = [
            ("electronics", "Electronic devices and gadgets"),
            ("clothing", "Apparel and accessories"),
            ("books", "Books and publications"),
            ("home", "Home and kitchen items"),
        ]

        type_ids = []
        for name, desc in types_data:
            result = self.db.table("types").call("add", name, desc, autocommit=False)
            if result["success"]:
                type_ids.append(result["id"])

        # Articles (5 per type)
        articles_data = [
            # Electronics
            ("LAPTOP001", 'MacBook Pro 16"', 2499.00),
            ("PHONE001", "iPhone 15 Pro", 1199.00),
            ("TABLET001", "iPad Air", 599.00),
            ("MOUSE001", "Wireless Mouse", 29.99),
            ("KEYB001", "Mechanical Keyboard", 149.00),
            # Clothing
            ("SHIRT001", "Cotton T-Shirt", 19.99),
            ("JEANS001", "Denim Jeans", 59.99),
            ("JACKET001", "Winter Jacket", 129.00),
            ("SHOES001", "Running Shoes", 89.99),
            ("HAT001", "Baseball Cap", 24.99),
            # Books
            ("BOOK001", "Python Programming", 49.99),
            ("BOOK002", "Data Science Handbook", 39.99),
            ("BOOK003", "Machine Learning Basics", 44.99),
            ("BOOK004", "Web Development Guide", 34.99),
            ("BOOK005", "Database Design", 42.99),
            # Home
            ("COFFEE001", "Coffee Maker", 79.99),
            ("BLENDER001", "High-Speed Blender", 99.99),
            ("LAMP001", "LED Desk Lamp", 45.00),
            ("CHAIR001", "Office Chair", 249.00),
            ("DESK001", "Standing Desk", 399.00),
        ]

        article_ids = []
        for i, (code, desc, price) in enumerate(articles_data):
            type_idx = i // 5  # 5 articles per type
            result = self.db.table("articles").call(
                "add", type_ids[type_idx], code, desc, price, autocommit=False
            )
            if result["success"]:
                article_ids.append(result["id"])

        # Purchases (120 total, distributed randomly)
        purchase_count = 0
        for _ in range(120):
            article_id = random.choice(article_ids)
            quantity = random.randint(1, 10)
            result = self.db.table("purchases").call("add", article_id, quantity, autocommit=False)
            if result["success"]:
                purchase_count += 1

        # Commit all changes
        self.db.commit()

        return {
            "success": True,
            "types": len(type_ids),
            "articles": len(article_ids),
            "purchases": purchase_count,
        }


if __name__ == "__main__":
    # Example: multiple Shop instances with different databases
    # Each instance is completely independent with its own connection pool
    myapp = Shop("sqlite:shop1.db")
    mysecond_app = Shop("sqlite:shop2.db")

    # You can work with both shops independently:
    # - Copy articles from one shop to another
    # - Compare prices across different databases
    # - Migrate data between instances
    # - Run parallel operations on separate databases
    #
    # Example: copy an article type from shop1 to shop2
    # type_result = myapp.db.table('types').get(1)
    # if type_result['success']:
    #     t = type_result['type']
    #     mysecond_app.db.table('types').add(t['name'], t['description'])
