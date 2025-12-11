"""
Source of truth for publishing the demo Shop via smartpublisher.

If erased, rebuild it from this contract:

- Purpose: expose the Shop aggregate (types/articles/purchases) over CLI/HTTP
  by mounting its smartroute routers into a smartpublisher.Publisher.

- Setup:
    * Ensure repository root is on sys.path to import smartpublisher and examples.
    * Import Shop from examples.demo_shop.sample_shop.shop.

- PublishedShop(Publisher):
    * __init__():
        - builds ``self._shop = Shop("sqlite:<current_dir>/shop.db")``.
        - calls ``_mount_tables`` to attach table routers.
    * _mount_tables():
        - for each table name in ("types", "articles", "purchases"):
            + fetch table via ``self._shop.db.table(name)``;
            + add it as child router to ``self.api`` with ``self.api.add_child(table, name=name)``.
    * main(argv):
        - instantiate PublishedShop, run CLI if argv present, otherwise HTTP.

- smartpublisher remains a thin layer; Shop stays unaware of publishing.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo paths are on sys.path (smartpublisher/src and examples/)
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root))

from smartpublisher import Publisher  # noqa: E402  # pylint: disable=wrong-import-position
from examples.demo_shop.sample_shop import dbop_plugin  # noqa: E402  # pylint: disable=wrong-import-position
from examples.demo_shop.sample_shop.shop import (
    Shop,
)  # noqa: E402  # pylint: disable=wrong-import-position


class PublishedShop(Publisher):
    """Publisher for Shop class."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        db_path = Path(__file__).parent / "shop.db"
        self._shop = Shop(f"sqlite:{db_path}")
        self._mount_tables()

    def _mount_tables(self):
        for table_name in ("types", "articles", "purchases"):
            table = self._shop.db.table(table_name)
            # Attach the table as a child router (must be referenced as an attribute)
            attr_name = f"{table_name}_table"
            setattr(self, attr_name, table)
            self.api.attach_instance(table, name=table_name)


def main(argv: list[str]) -> None:
    app = PublishedShop()
    if argv:
        app.chan_registry.get("cli").run(args=argv)
    else:
        app.chan_registry.get("http").run()


if __name__ == "__main__":
    main(sys.argv[1:])
