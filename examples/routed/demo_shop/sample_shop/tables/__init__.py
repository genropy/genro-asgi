"""Table handler classes for shop database."""

from .article_types import ArticleTypes
from .articles import Articles
from .purchases import Purchases

__all__ = [
    "ArticleTypes",
    "Articles",
    "Purchases",
]
