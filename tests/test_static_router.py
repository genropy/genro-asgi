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

    def test_node_nonexistent_file_fallback_to_root(
        self, temp_storage_with_files: LocalStorage
    ) -> None:
        """Best-match: nonexistent file falls back to root with extra_args."""
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("nonexistent.txt")
        # Best-match: falls back to root directory
        assert router_node.callable is not None
        assert router_node.extra_args == ["nonexistent.txt"]
        storage_node = router_node()
        assert storage_node.isdir  # Root is a directory

    def test_node_nested_file(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("images/logo.png")
        assert router_node.callable is not None
        storage_node = router_node()
        assert storage_node.basename == "logo.png"
        assert storage_node.mimetype == "image/png"

    def test_node_empty_path_returns_root(
        self, temp_storage_with_files: LocalStorage
    ) -> None:
        """Empty path returns root directory node."""
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("")
        assert router_node.callable is not None
        storage_node = router_node()
        assert storage_node.isdir
        assert router_node.extra_args == []

    def test_node_directory_returns_directory_node(
        self, temp_storage_with_files: LocalStorage
    ) -> None:
        """Best-match: directory path returns directory node."""
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("images")
        assert router_node.callable is not None
        assert router_node.type == "router"  # Directory = router type
        storage_node = router_node()
        assert storage_node.isdir
        assert storage_node.basename == "images"

    def test_node_partial_path_with_extra_args(
        self, temp_storage_with_files: LocalStorage
    ) -> None:
        """Best-match: partial path returns deepest valid node with extra_args."""
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        # images exists, but gamma/123 don't
        router_node = router.node("images/gamma/123")
        assert router_node.callable is not None
        assert router_node.extra_args == ["gamma", "123"]
        storage_node = router_node()
        assert storage_node.basename == "images"

    def test_node_with_query_string(
        self, temp_storage_with_files: LocalStorage
    ) -> None:
        """Query string is parsed into partial_kwargs."""
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        router_node = router.node("images/logo.png?size=large&format=webp")
        assert router_node.callable is not None
        assert router_node.partial_kwargs == {"size": "large", "format": "webp"}
        storage_node = router_node()
        assert storage_node.basename == "logo.png"

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
        # In lazy mode, routers are StaticRouter instances (router references)
        assert isinstance(result["routers"]["images"], StaticRouter)

    def test_nodes_root_info(self, temp_storage_with_files: LocalStorage) -> None:
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root, name="static")
        result = router.nodes()
        assert result["name"] == "static"
        assert result["router"] is router
        assert "description" in result  # Has description instead of root

    def test_nodes_with_pattern(self, temp_storage_with_files: LocalStorage) -> None:
        """Pattern filters entries by regex."""
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        # Only match .css files
        result = router.nodes(pattern=r"\.css$")
        assert "style.css" in result.get("entries", {})
        assert "index.html" not in result.get("entries", {})

    def test_nodes_with_basepath(self, temp_storage_with_files: LocalStorage) -> None:
        """Basepath navigates to subdirectory."""
        root = temp_storage_with_files.node("site")
        router = StaticRouter(root)
        result = router.nodes(basepath="images")
        # Should return contents of images/ directory
        assert "logo.png" in result.get("entries", {})


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
