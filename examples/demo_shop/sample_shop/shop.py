"""
Shop - RoutedClass aggregate for demo_shop.

Mounts table managers (types, articles, purchases) as child routers.
Can be mounted via config.yaml as an app in AsgiServer.
"""

import csv
import importlib
import random
from pathlib import Path

from genro_routes import RoutedClass, Router, route

from .sql import Table, SqlDb


class Shop(RoutedClass):
    """Shop aggregate - exposes tables via router."""

    title = "Shop API"
    version = "1.0.0"

    def __init__(self, connection_string: str = "sqlite:shop.db", **kwargs):
        self.connection_string = connection_string
        self.app_dir = kwargs.get("app_dir", Path(__file__).parent.parent)
        self.api = Router(self, name="api")

        # Auto-discover table classes
        self.tables = self._configure_tables()

        # Create database and register tables
        self.db = SqlDb(connection_string, self)
        for table_cls in self.tables:
            self.db.add_table(table_cls)

        # Mount tables as child routers
        for name, instance in self.db.tables.items():
            setattr(self, f"{name}_table", instance)
            self.api.attach_instance(instance, name=name)

        self.db.adapter.check_structure()

    def _configure_tables(self) -> list[type[Table]]:
        """Auto-discover Table subclasses from tables/ folder."""
        tables_dir = Path(__file__).parent / "tables"
        result = []

        for py_file in tables_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f".tables.{py_file.stem}"
            module = importlib.import_module(module_name, package=__package__)

            for name in dir(module):
                cls = getattr(module, name)
                if isinstance(cls, type) and issubclass(cls, Table) and cls is not Table:
                    result.append(cls)

        return result

    @route("api")
    def info(self):
        """Return shop info."""
        table_names = [t.name for t in self.tables]
        return {
            "status": "ok",
            "connection": self.connection_string,
            "tables": table_names,
        }

    @route("api")
    def populate(self):
        """Populate database with sample data from CSV files."""
        resources_dir = Path(__file__).parent / "resources"
        type_ids = {}
        article_ids = []
        types_count = 0
        articles_count = 0
        purchases_count = 0

        # Load article types
        types_csv = resources_dir / "article_types.csv"
        with open(types_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                result = self.db.tables["article_type"].add(
                    name=row["name"],
                    description=row["description"]
                )
                if result.get("id"):
                    type_ids[row["name"]] = result["id"]
                    types_count += 1

        # Load articles
        articles_csv = resources_dir / "articles.csv"
        with open(articles_csv) as f:
            reader = csv.DictReader(f)
            for row in reader:
                type_id = type_ids.get(row["type"])
                if type_id:
                    result = self.db.tables["article"].add(
                        article_type_id=type_id,
                        code=row["code"],
                        description=row["description"],
                        price=float(row["price"])
                    )
                    if result.get("id"):
                        article_ids.append(result["id"])
                        articles_count += 1

        # Generate random purchases
        for article_id in article_ids:
            for _ in range(random.randint(1, 5)):
                self.db.tables["purchase"].add(
                    article_id=article_id,
                    quantity=random.randint(1, 10)
                )
                purchases_count += 1

        return {
            "status": "ok",
            "types": types_count,
            "articles": articles_count,
            "purchases": purchases_count,
        }


if __name__ == "__main__":
    shop = Shop("sqlite:test.db")
    result = shop.api.call("info")
    print(result)
