"""Deployment recipe for the genro-cocktail prototype.

Run with:  genro-asgi serve config.py
(the launcher puts this directory on sys.path, so the sibling imports work).

The database path can be overridden with the GENRO_COCKTAIL_DB environment
variable — an EnvResolver stored in place, resolved at read time.
"""

from genro_asgi.config import AsgiConfigBuilder
from genro_bag.resolvers import EnvResolver

from app import CocktailApp
from db import CocktailDb


class ServerConfiguration(AsgiConfigBuilder):
    """Genro Cocktail — BOM management for a mixology lab (prototype)."""

    def main(self, root):
        cfg = root.configuration()
        cfg.server(host="127.0.0.1", port=8075).session(ttl=3600)
        cfg.applications(default="cocktail").application(
            code="cocktail", mount="", app_class=CocktailApp
        )
        cfg.databases().database(
            code="default",
            db_class=CocktailDb,
            path=EnvResolver("GENRO_COCKTAIL_DB", default="cocktail.db"),
        )
