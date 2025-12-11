"""
Test set per l'uso diretto di Shop con i router smartroute attivi.

Obiettivi:
- Verificare CRUD su types/articles/purchases con plugin dbop+pydantic.
- Coprire transazioni/autocommit e statistiche.
"""

import os
import tempfile

import pytest

from examples.demo_shop.sample_shop.shop import Shop


@pytest.fixture
def temp_db():
    """Database temporaneo per ogni test."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name
    os.environ["SHOP_DB_PATH"] = db_path
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def shop(temp_db):
    return Shop(f"sqlite:{temp_db}")


class TestTypes:
    def test_add_and_list(self, shop):
        shop.db.table("types").call("add", "elect", "Electronic devices")
        shop.db.table("types").call("add", "books", "Books")

        result = shop.db.table("types").call("list")
        assert result["success"]
        assert result["count"] == 2


class TestArticles:
    def test_add_and_get(self, shop):
        type_id = shop.db.table("types").call("add", "electronics", "").get("id")
        result = shop.db.table("articles").call("add", type_id, "LAPTOP001", "MacBook Pro", 2499.00)
        assert result["success"]
        gid = result["id"]

        fetched = shop.db.table("articles").call("get", gid)
        assert fetched["success"]
        assert fetched["article"]["code"] == "LAPTOP001"

    def test_validation(self, shop):
        type_id = shop.db.table("types").call("add", "electronics", "").get("id")
        with pytest.raises(Exception):
            shop.db.table("articles").call("add", type_id, "BAD", "Bad", -1)


class TestPurchases:
    def _seed_article(self, shop):
        type_id = shop.db.table("types").call("add", "electronics", "").get("id")
        art = shop.db.table("articles").call("add", type_id, "MOUSE001", "Mouse", 29.99)
        return art["id"]

    def test_add_purchase(self, shop):
        art_id = self._seed_article(shop)
        result = shop.db.table("purchases").call("add", art_id, 3)
        assert result["success"]
        assert result["quantity"] == 3

    def test_statistics(self, shop):
        art_id = self._seed_article(shop)
        shop.db.table("purchases").call("add", art_id, 2)
        shop.db.table("purchases").call("add", art_id, 1)
        stats = shop.db.table("purchases").call("statistics")
        assert stats["success"]
        assert stats["total_purchases"] == 2


class TestTransactions:
    def test_autocommit_true(self, shop):
        res = shop.db.table("types").call("add", "electronics", autocommit=True)
        assert res["success"]
        listed = shop.db.table("types").call("list")
        assert listed["count"] == 1

    def test_manual_commit(self, shop):
        shop.db.table("types").call("add", "electronics", autocommit=False)
        shop.db.commit()
        listed = shop.db.table("types").call("list")
        assert listed["count"] == 1


class TestRouterIntrospection:
    def test_entries(self, shop):
        entries = shop.db.table("types").api.entries()
        assert {"add", "remove", "list", "get"} <= set(entries)

    def test_logging_configurable(self, shop):
        assert hasattr(shop.db.table("types").api, "logging")
        shop.db.table("types").api.logging.set_config(mode="verbose")
        shop.db.table("types").api.logging.set_config(mode="silent")
