"""
Sample shop application - SQLite-based e-commerce example.

KEY CONCEPT:
- The Shop class and table managers are NORMAL Python classes
- They use smartswitch for method dispatch and validation
- They work perfectly fine WITHOUT smpub
- smpub is OPTIONAL - it just publishes them for CLI/HTTP access

This is a STANDALONE Python library. You can use it directly:
    from sample_shop import Shop
    shop = Shop()
    shop.articles.add(...)

See:
- example_pythonic.py: Pure Python usage (no smpub)
- shop_usage.ipynb: Interactive Jupyter notebook
- ../published_shop/: OPTIONAL smpub publishing (separate folder!)
- ../PLUGINS_EXPLANATION.md: How smartswitch plugins reduce boilerplate (shared)
"""

from .sql import SqlDb, DB_PATH
from .shop import Shop
from .tables import ArticleTypes, Articles, Purchases
# Register demo plugin (dbop) on import
from . import dbop_plugin  # noqa: F401

__all__ = [
    "SqlDb",
    "DB_PATH",
    "Shop",
    "ArticleTypes",
    "Articles",
    "Purchases",
]
