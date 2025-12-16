"""Table handler classes for shop database."""

from .article_type import ArticleType
from .article import Article
from .purchase import Purchase

__all__ = [
    "ArticleType",
    "Article",
    "Purchase",
]
