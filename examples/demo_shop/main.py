"""
Shop - Demo e-commerce application.

Mounts table managers (article_type, article, purchase) as child routers.
Can be mounted via config.yaml as an app in AsgiServer.
"""

import csv
import importlib
import random
import sys
from pathlib import Path

# Add base_dir to sys.path for submodule imports (when run directly)
_base_dir = Path(__file__).parent
if str(_base_dir) not in sys.path:
    sys.path.insert(0, str(_base_dir))

from genro_routes import route

from genro_asgi import AsgiApplication

from sql import Table, SqlDb


class Shop(AsgiApplication):
    """Shop application - exposes tables via router."""

    openapi_info = {
        "title": "Shop API",
        "version": "1.0.0",
        "description": "Demo e-commerce API",
    }

    def on_init(self, connection_string: str = "sqlite:shop.db", **kwargs):
        self.connection_string = connection_string
        self.tables = self._configure_tables()
        self.db = SqlDb(connection_string, self)
        for table_cls in self.tables:
            self.db.add_table(table_cls)
        self.db.attach_tables()
        self.db.adapter.check_structure()

    def _configure_tables(self) -> list[type[Table]]:
        """Auto-discover Table subclasses from tables/ folder."""
        tables_dir = self.base_dir / "tables"
        result = []

        for py_file in tables_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"tables.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for name in dir(module):
                cls = getattr(module, name)
                if isinstance(cls, type) and issubclass(cls, Table) and cls is not Table:
                    result.append(cls)

        return result

    @route()
    def info(self):
        """Return shop info."""
        table_names = [t.name for t in self.tables]
        return {
            "status": "ok",
            "connection": self.connection_string,
            "tables": table_names,
        }

    @route()
    def populate(self):
        """Populate database with sample data from CSV files."""
        resources_dir = self.resources_path
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
    pass
