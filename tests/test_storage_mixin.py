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

"""StorageMixin + ``storage`` config section tests (Macro 3 Phase 2).

Two layers: the capability mixin (``storage=``/``storage_key=`` peeled by
``AsgiServer``, the plain ``BaseServer`` never gaining a ``storage`` attribute)
and the config path (a recipe's ``storage`` section reaching the server's
``LocalStorage`` through ``AsgiServer(config=...)``, an explicit kwarg still
winning over the configured one).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from genro_asgi import (
    AsgiConfigBuilder,
    AsgiServer,
    BaseApplication,
    BaseServer,
    LocalStorage,
    StorageMixin,
)
from genro_asgi.middleware.base import BaseMiddleware
from genro_asgi.types import Receive, Scope, Send


class ShopApp(BaseApplication):
    """Minimal primary app for the config-driven tests."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"shop"})


@pytest.fixture
def key() -> str:
    """A single fresh Fernet key."""
    return Fernet.generate_key().decode()


def chain_types(server: AsgiServer) -> list[str]:
    """The class names of the middlewares in the server's chain, outermost first."""
    names: list[str] = []
    node: object = server.middleware_chain
    while isinstance(node, BaseMiddleware):
        names.append(type(node).__name__)
        node = node.app
    return names


class TestMixinComposition:
    def test_default_storage_is_localstorage_with_predefined_mounts(self) -> None:
        server = AsgiServer(applications=[BaseApplication(mount="")])
        assert isinstance(server.storage, LocalStorage)
        assert server.storage.has_mount("site")
        assert server.storage.has_mount("secure")

    def test_localstorage_instance_is_adopted_as_is(self, tmp_path: Path) -> None:
        provided = LocalStorage(base_dir=str(tmp_path))
        server = AsgiServer(applications=[BaseApplication(mount="")], storage=provided)
        assert server.storage is provided

    def test_dict_config_materializes_mounts(self, tmp_path: Path) -> None:
        server = AsgiServer(
            applications=[BaseApplication(mount="")],
            storage={"data": {"path": str(tmp_path / "data")}},
        )
        node = server.storage.node("data:hello.txt")
        node.write_text("hi")
        assert node.read_text() == "hi"

    def test_base_server_has_no_storage_attribute(self) -> None:
        assert not hasattr(BaseServer(applications=[BaseApplication(mount="")]), "storage")


class TestStorageKey:
    def test_storage_key_installs_keys_secure_roundtrip(self, tmp_path: Path, key: str) -> None:
        server = AsgiServer(
            applications=[BaseApplication(mount="")],
            storage=LocalStorage(base_dir=str(tmp_path)),
            storage_key=key,
        )
        assert server.storage.encryption_active
        node = server.storage.node("secure:plugin.json")
        node.write_text('{"k": 1}')
        on_disk = (tmp_path / "secure" / "plugin.json").read_bytes()
        assert on_disk != b'{"k": 1}'
        assert node.read_text() == '{"k": 1}'

    def test_empty_storage_key_raises_at_construction(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            AsgiServer(
                applications=[BaseApplication(mount="")],
                storage=LocalStorage(base_dir=str(tmp_path)),
                storage_key="",
            )

    def test_omitted_storage_key_leaves_encryption_dormant(self, tmp_path: Path) -> None:
        server = AsgiServer(
            applications=[BaseApplication(mount="")],
            storage=LocalStorage(base_dir=str(tmp_path)),
        )
        assert not server.storage.encryption_active


class TestBareMixin:
    def test_mixin_over_base_server_exposes_storage(self) -> None:
        class Srv(StorageMixin, BaseServer):
            pass

        server = Srv(applications=[BaseApplication(mount="")])
        assert isinstance(server.storage, LocalStorage)


class TestConfigDriven:
    def test_recipe_storage_section_serves_declared_mounts(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"

        class StorageConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000)
                cfg.storage().mount(code="data", path=str(data_dir))
                cfg.applications(default="shop").application(code="shop", app_class=ShopApp)

        server = AsgiServer(config=StorageConfig)
        node = server.storage.node("data:file.txt")
        node.write_text("x")
        assert node.read_text() == "x"

    def test_recipe_storage_key_installs_encryption(self, tmp_path: Path, key: str) -> None:
        secure_root = tmp_path

        class StorageConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000, storage_key=key)
                cfg.storage().mount(code="site", path=str(secure_root))
                cfg.applications(default="shop").application(code="shop", app_class=ShopApp)

        server = AsgiServer(config=StorageConfig)
        assert server.storage.encryption_active

    def test_explicit_kwarg_wins_over_the_configured_one(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        override_dir = tmp_path / "override"

        class StorageConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000)
                cfg.storage().mount(code="data", path=str(data_dir))
                cfg.applications(default="shop").application(code="shop", app_class=ShopApp)

        server = AsgiServer(
            config=StorageConfig, storage={"only": {"path": str(override_dir)}}
        )
        assert server.storage.node("only:w.txt") is not None
        with pytest.raises(ValueError, match="data"):
            server.storage.node("data:w.txt")
