# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for StaticRouter - storage-backed router."""

from pathlib import Path
import pytest
from genro_asgi.storage import LocalStorage, StorageNode
from genro_asgi.routers import StaticRouter


@pytest.fixture
def temp_storage(tmp_path: Path) -> LocalStorage:
    """Create a LocalStorage with temp directory as base."""
    return LocalStorage(base_dir=tmp_path)


@pytest.fixture
def temp_storage_with_files(temp_storage: LocalStorage, tmp_path: Path) -> LocalStorage:
    """Create storage with test files."""
    # Create test structure
    (tmp_path / "index.html").write_text("<html>index</html>")
    (tmp_path / "style.css").write_text("body { color: red; }")
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "logo.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "app.js").write_text("console.log('hello');")
    return temp_storage


class TestStaticRouterBasic:
    """Basic StaticRouter tests."""

    def test_init_with_storage_node(self, temp_storage: LocalStorage) -> None:
        root = temp_storage.node("site")
        router = StaticRouter(root)
        assert router._root is root
        assert router.name is None
        assert router._html_index is True

    def test_init_with_name(self, temp_storage: LocalStorage) -> None:
        root = temp_storage.node("site")
        router = StaticRouter(root, name="static")
        assert router.name == "static"

    def test_init_html_index_false(self, temp_storage: LocalStorage) -> None:
        root = temp_storage.node("site")
        router = StaticRouter(root, html_index=False)
        assert router._html_index is False


class TestStaticRouterNode:
    """Tests for StaticRouter.node() method."""

    def test_node_existing_file(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("style.css")
        assert router_node
        assert router_node.callable is not None
        # Call the handler to get StorageNode
        storage_node = router_node()
        assert storage_node.basename == "style.css"
        assert storage_node.mimetype == "text/css"

    def test_node_nonexistent_file(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("nonexistent.txt")
        assert router_node.callable is None  # Empty RouterNode

    def test_node_nested_file(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("images/logo.png")
        assert router_node.callable is not None
        storage_node = router_node()
        assert storage_node.basename == "logo.png"
        assert storage_node.mimetype == "image/png"

    def test_node_index_html_default(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        # Empty path should resolve to index.html
        router_node = router.node("")
        assert router_node.callable is not None
        storage_node = router_node()
        assert storage_node.basename == "index.html"

    def test_node_index_keyword(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("index")
        assert router_node.callable is not None
        storage_node = router_node()
        assert storage_node.basename == "index.html"

    def test_node_no_html_index(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root, html_index=False)
        router_node = router.node("")
        assert router_node.callable is None  # No default index

    def test_node_directory_returns_empty(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        # Directory should not be returned as file
        router_node = router.node("images")
        assert router_node.callable is None

    def test_node_returns_storage_node(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("style.css")
        storage_node = router_node()
        # Verify it's a proper StorageNode
        assert isinstance(storage_node, StorageNode)
        assert storage_node.exists
        assert storage_node.isfile


class TestStaticRouterNodes:
    """Tests for StaticRouter.nodes() method."""

    def test_nodes_lists_files(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        result = router.nodes()
        assert "entries" in result
        assert "index.html" in result["entries"]
        assert "style.css" in result["entries"]
        assert result["entries"]["style.css"]["mimetype"] == "text/css"

    def test_nodes_lists_directories(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        result = router.nodes()
        assert "routers" in result
        assert "images" in result["routers"]
        assert "js" in result["routers"]

    def test_nodes_nested_structure(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        result = router.nodes()
        # images subdirectory should have logo.png
        images_nodes = result["routers"]["images"]
        assert "entries" in images_nodes
        assert "logo.png" in images_nodes["entries"]

    def test_nodes_empty_directory(self, temp_storage: LocalStorage, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        root = temp_storage.node("site:empty")
        router = StaticRouter(root)
        result = router.nodes()
        assert result == {}

    def test_nodes_nonexistent_directory(self, temp_storage: LocalStorage) -> None:
        root = temp_storage.node("site:nonexistent")
        router = StaticRouter(root)
        result = router.nodes()
        assert result == {}

    def test_nodes_skips_hidden_files(
        self, temp_storage_with_files: LocalStorage, tmp_path: Path
    ) -> None:
        (tmp_path / ".hidden").write_text("hidden")
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        result = router.nodes()
        assert ".hidden" not in result.get("entries", {})

    def test_nodes_lazy_mode(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        result = router.nodes(lazy=True)
        # In lazy mode, routers are callables
        assert callable(result["routers"]["images"])

    def test_nodes_root_info(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root, name="static")
        result = router.nodes()
        assert result["name"] == "static"
        assert result["router"] is router
        assert result["root"] == "site"


class TestStaticRouterInterface:
    """Tests for RouterInterface compliance."""

    def test_values_returns_empty(self, temp_storage: LocalStorage) -> None:
        root = temp_storage.node("site")
        router = StaticRouter(root)
        assert list(router.values()) == []

    def test_on_attached_to_parent_noop(self, temp_storage: LocalStorage) -> None:
        root = temp_storage.node("site")
        router = StaticRouter(root)
        # Should not raise
        router._on_attached_to_parent(None)


class TestStaticRouterReadContent:
    """Tests for reading file content via StorageNode."""

    def test_read_text_file(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("style.css")
        storage_node = router_node()
        content = storage_node.read_text()
        assert content == "body { color: red; }"

    def test_read_binary_file(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("images/logo.png")
        storage_node = router_node()
        content = storage_node.read_bytes()
        assert content.startswith(b"\x89PNG")
