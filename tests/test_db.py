# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""DB handler tests (core 1b Phase 6): ``AsgiDbHandlerBase`` proxy, the server
registry, and config materialization of the ``databases`` section.
"""

from __future__ import annotations

from typing import Any

import pytest

from genro_asgi import (
    AsgiConfigBuilder,
    AsgiDbHandlerBase,
    AsgiServer,
    BaseApplication,
    BaseServer,
    ConfigurationHandler,
)


class FakeDb:
    """Minimal db: holds params, exposes execute and closeConnection."""

    def __init__(self, **params: Any) -> None:
        self.params = params
        self.closed = False

    def execute(self, sql: str) -> str:
        return f"ran: {sql}"

    def closeConnection(self) -> None:
        self.closed = True


class TestAsgiDbHandlerBase:
    def test_proxies_attribute(self) -> None:
        """A non-underscore attribute is fetched from the wrapped db."""
        db = FakeDb(dbname="shop")
        handler = AsgiDbHandlerBase(db)
        assert handler.params is db.params

    def test_proxies_method(self) -> None:
        """A method call is forwarded to the wrapped db."""
        handler = AsgiDbHandlerBase(FakeDb())
        assert handler.execute("SELECT 1") == "ran: SELECT 1"

    def test_close_connection_delegates(self) -> None:
        """closeConnection delegates to the wrapped db when present."""
        db = FakeDb()
        AsgiDbHandlerBase(db).closeConnection()
        assert db.closed is True

    def test_close_connection_noop_when_absent(self) -> None:
        """closeConnection is a no-op when the db has none."""

        class Bare:
            pass

        AsgiDbHandlerBase(Bare()).closeConnection()  # must not raise

    def test_underscore_attributes_not_proxied(self) -> None:
        """Underscore names raise AttributeError instead of proxying (no recursion)."""
        handler = AsgiDbHandlerBase(FakeDb())
        with pytest.raises(AttributeError):
            handler._missing

    def test_missing_attribute_raises(self) -> None:
        """A public attribute the db lacks raises AttributeError."""
        handler = AsgiDbHandlerBase(FakeDb())
        with pytest.raises(AttributeError):
            handler.nonexistent

    def test_repr_shows_wrapped_type(self) -> None:
        """repr names the handler and the wrapped db type."""
        assert repr(AsgiDbHandlerBase(FakeDb())) == "AsgiDbHandlerBase(FakeDb)"

    def test_subclass_inherits_proxy(self) -> None:
        """A custom handler subclass keeps the proxy behaviour."""

        class CustomHandler(AsgiDbHandlerBase):
            pass

        handler = CustomHandler(FakeDb(dbname="x"))
        assert handler.params == {"dbname": "x"}
        assert isinstance(handler, AsgiDbHandlerBase)


class TestDatabaseRegistry:
    def test_add_database_registers_by_code(self) -> None:
        server = BaseServer(primary=BaseApplication())
        handler = AsgiDbHandlerBase(FakeDb())
        server.add_database("shop", handler)
        assert server.databases == {"shop": handler}

    def test_add_database_duplicate_code_raises(self) -> None:
        server = BaseServer(primary=BaseApplication())
        server.add_database("shop", AsgiDbHandlerBase(FakeDb()))
        with pytest.raises(ValueError):
            server.add_database("shop", AsgiDbHandlerBase(FakeDb()))

    def test_databases_empty_by_default(self) -> None:
        assert BaseServer(primary=BaseApplication()).databases == {}


# --- config-driven materialization ---


class ShopApp(BaseApplication):
    pass


class TwoDatabaseConfig(AsgiConfigBuilder):
    """A recipe with two ``database`` entries over ``FakeDb``."""

    def main(self, root: Any) -> None:
        root.server(host="127.0.0.1", port=8000)
        apps = root.applications(default="shop")
        apps.application(code="shop", app_class=ShopApp)
        dbs = root.databases()
        dbs.database(code="shop", db_class=FakeDb, dbname="shop")
        dbs.database(code="reports", db_class=FakeDb, db_handler_class=AsgiDbHandlerBase, dbname="ro")


class TestDatabasesMaterialization:
    def test_materialize_registers_both_handlers(self) -> None:
        server = ConfigurationHandler(TwoDatabaseConfig(name="config")).materialize()
        assert isinstance(server, AsgiServer)
        assert set(server.databases) == {"shop", "reports"}
        shop = server.databases["shop"]
        assert isinstance(shop, AsgiDbHandlerBase)
        assert shop.params == {"dbname": "shop"}
        assert shop.execute("SELECT 1") == "ran: SELECT 1"
        reports = server.databases["reports"]
        assert reports.params == {"dbname": "ro"}

    def test_worker_projection_retains_databases_section(self) -> None:
        handler = ConfigurationHandler(TwoDatabaseConfig(name="config"))
        worker = handler.materialize(role="worker", app="shop")
        assert set(worker.databases) == {"shop", "reports"}

    def test_database_missing_db_class_raises(self) -> None:
        class MissingDbClassConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.server(host="127.0.0.1", port=8000)
                apps = root.applications(default="shop")
                apps.application(code="shop", app_class=ShopApp)
                dbs = root.databases()
                dbs.database(code="shop")

        with pytest.raises(ValueError):
            ConfigurationHandler(MissingDbClassConfig(name="config")).materialize()
