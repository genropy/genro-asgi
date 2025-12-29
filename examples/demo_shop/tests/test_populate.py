"""
Test popolamento seed del demo shop.

Verifica che populateDb crei i record attesi e che le statistiche siano coerenti.
"""

import os
import tempfile

import pytest

from examples.demo_shop.sample_shop.shop import Shop


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name
    os.environ["SHOP_DB_PATH"] = db_path
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def shop(temp_db):
    return Shop(f"sqlite:{temp_db}")


def test_populate_counts(shop):
    result = shop.populateDb()
    assert result == {"success": True, "types": 4, "articles": 20, "purchases": 120}


def test_populate_data(shop):
    shop.populateDb()
    types = shop.db.table("types").call("list")
    articles = shop.db.table("articles").call("list")
    purchases = shop.db.table("purchases").call("list")
    assert types["count"] == 4
    assert articles["count"] == 20
    assert purchases["count"] == 120


def test_populate_stats(shop):
    shop.populateDb()
    stats = shop.db.table("purchases").call("statistics")
    assert stats["success"]
    assert stats["total_purchases"] == 120
    assert stats["total_revenue"] > 0
    assert stats["top_articles"]
