# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for LocalStorage - filesystem-only storage."""

from pathlib import Path
import pytest
from genro_asgi.storage import LocalStorage, LocalStorageNode


@pytest.fixture
def temp_storage(tmp_path: Path) -> LocalStorage:
    """Create a LocalStorage with a temporary mount."""
    storage = LocalStorage(base_dir=tmp_path)
    storage.add_mount({"name": "test", "type": "local", "path": str(tmp_path)})
    return storage


@pytest.fixture
def temp_storage_with_files(temp_storage: LocalStorage, tmp_path: Path) -> LocalStorage:
    """Create storage with some test files."""
    # Create test files
    (tmp_path / "file.txt").write_text("hello")
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "logo.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "style.css").write_text("body { color: red; }")
    return temp_storage


class TestLocalStorageNode:
    """Tests for LocalStorageNode."""

    def test_fullpath(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:resources/logo.png")
        assert node.fullpath == "test:resources/logo.png"

    def test_fullpath_no_path(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test")
        assert node.fullpath == "test"

    def test_path(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:images/logo.png")
        assert node.path == "images/logo.png"

    def test_exists_true(
        self, temp_storage_with_files: LocalStorage, tmp_path: Path
    ) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.exists is True

    def test_exists_false(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:nonexistent.txt")
        assert node.exists is False

    def test_isfile(
        self, temp_storage_with_files: LocalStorage, tmp_path: Path
    ) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.isfile is True
        assert node.isdir is False

    def test_isdir(
        self, temp_storage_with_files: LocalStorage, tmp_path: Path
    ) -> None:
        node = temp_storage_with_files.node("test:images")
        assert node.isdir is True
        assert node.isfile is False

    def test_size(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.size == 5  # "hello" is 5 bytes

    def test_size_nonexistent(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:nonexistent.txt")
        assert node.size == 0

    def test_basename(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:images/logo.png")
        assert node.basename == "logo.png"

    def test_suffix(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:images/logo.png")
        assert node.suffix == ".png"

    def test_ext(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:images/logo.png")
        assert node.ext == "png"

    def test_mimetype_png(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:images/logo.png")
        assert node.mimetype == "image/png"

    def test_mimetype_css(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:style.css")
        assert node.mimetype == "text/css"

    def test_mimetype_unknown(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:file.xyz123")
        assert node.mimetype == "application/octet-stream"

    def test_parent(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:images/logo.png")
        parent = node.parent
        assert parent.path == "images"

    def test_parent_root(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:file.txt")
        parent = node.parent
        assert parent.path == ""

    def test_read_text(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.read_text() == "hello"

    def test_read_bytes(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test:images/logo.png")
        content = node.read_bytes()
        assert content.startswith(b"\x89PNG")

    def test_read_mode_text(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.read(mode="r") == "hello"

    def test_read_mode_binary(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.read(mode="rb") == b"hello"

    def test_write_text(self, temp_storage: LocalStorage, tmp_path: Path) -> None:
        node = temp_storage.node("test:new_file.txt")
        result = node.write_text("new content")
        assert result is True
        assert (tmp_path / "new_file.txt").read_text() == "new content"

    def test_write_bytes(self, temp_storage: LocalStorage, tmp_path: Path) -> None:
        node = temp_storage.node("test:new_file.bin")
        result = node.write_bytes(b"\x00\x01\x02")
        assert result is True
        assert (tmp_path / "new_file.bin").read_bytes() == b"\x00\x01\x02"

    def test_write_creates_parent_dirs(
        self, temp_storage: LocalStorage, tmp_path: Path
    ) -> None:
        node = temp_storage.node("test:deep/nested/dir/file.txt")
        node.write_text("nested content")
        assert (tmp_path / "deep" / "nested" / "dir" / "file.txt").exists()

    def test_child(self, temp_storage: LocalStorage) -> None:
        parent = temp_storage.node("test:resources")
        child = parent.child("images", "logo.png")
        assert child.fullpath == "test:resources/images/logo.png"

    def test_child_from_root(self, temp_storage: LocalStorage) -> None:
        parent = temp_storage.node("test")
        child = parent.child("images", "logo.png")
        assert child.fullpath == "test:images/logo.png"

    def test_children(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test")
        children = node.children()
        names = sorted(c.basename for c in children)
        assert "file.txt" in names
        assert "images" in names
        assert "resources" in names

    def test_children_empty_dir(
        self, temp_storage: LocalStorage, tmp_path: Path
    ) -> None:
        (tmp_path / "empty_dir").mkdir()
        node = temp_storage.node("test:empty_dir")
        assert node.children() == []

    def test_children_file_returns_empty(
        self, temp_storage_with_files: LocalStorage
    ) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.children() == []


class TestLocalStorage:
    """Tests for LocalStorage manager."""

    def test_add_mount(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.add_mount({"name": "test", "type": "local", "path": str(tmp_path)})
        assert storage.has_mount("test")

    def test_add_mount_relative_path(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        storage.add_mount({"name": "rel", "type": "local", "path": "subdir"})
        assert storage.has_mount("rel")
        # The path should be resolved to absolute
        assert storage._mounts["rel"] == (tmp_path / "subdir").resolve()

    def test_add_mount_invalid_type(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        with pytest.raises(ValueError, match="only supports type='local'"):
            storage.add_mount({"name": "remote", "type": "s3", "bucket": "test"})

    def test_add_mount_duplicate(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.add_mount({"name": "test", "type": "local", "path": str(tmp_path)})
        with pytest.raises(ValueError, match="already exists"):
            storage.add_mount({"name": "test", "type": "local", "path": str(tmp_path)})

    def test_delete_mount(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.add_mount({"name": "test", "type": "local", "path": str(tmp_path)})
        storage.delete_mount("test")
        assert not storage.has_mount("test")

    def test_delete_mount_nonexistent(self) -> None:
        storage = LocalStorage()
        # Should not raise
        storage.delete_mount("nonexistent")

    def test_get_mount_names(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.add_mount({"name": "a", "type": "local", "path": str(tmp_path)})
        storage.add_mount({"name": "b", "type": "local", "path": str(tmp_path)})
        names = storage.get_mount_names()
        assert "a" in names
        assert "b" in names

    def test_has_mount(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.add_mount({"name": "test", "type": "local", "path": str(tmp_path)})
        assert storage.has_mount("test") is True
        assert storage.has_mount("other") is False

    def test_configure_from_list(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.configure(
            [
                {"name": "site", "type": "local", "path": str(tmp_path)},
                {"name": "data", "type": "local", "path": str(tmp_path / "data")},
            ]
        )
        assert storage.has_mount("site")
        assert storage.has_mount("data")

    def test_node_with_colon_syntax(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:resources/logo.png")
        assert node._mount == "test"
        assert node._path == "resources/logo.png"

    def test_node_with_parts(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test", "resources", "logo.png")
        assert node._mount == "test"
        assert node._path == "resources/logo.png"

    def test_node_mixed_syntax(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:resources", "images", "logo.png")
        assert node._mount == "test"
        assert node._path == "resources/images/logo.png"

    def test_node_mount_not_found(self) -> None:
        storage = LocalStorage()
        with pytest.raises(ValueError, match="not found"):
            storage.node("nonexistent:file.txt")

    def test_node_none_raises(self, temp_storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="required"):
            temp_storage.node(None)


class TestMountResolution:
    """Tests for _resolve_mount and predefined mount methods."""

    def test_resolve_mount_predefined_site(self, tmp_path: Path) -> None:
        """mount_site() method has priority over _mounts."""
        storage = LocalStorage(base_dir=tmp_path)
        assert storage._resolve_mount("site") == tmp_path

    def test_resolve_mount_config(self, tmp_path: Path) -> None:
        """Fallback to _mounts if method doesn't exist."""
        storage = LocalStorage()
        storage.add_mount({"name": "data", "type": "local", "path": str(tmp_path)})
        assert storage._resolve_mount("data") == tmp_path

    def test_resolve_mount_not_found(self) -> None:
        """ValueError if mount not found."""
        storage = LocalStorage()
        with pytest.raises(ValueError, match="Mount 'unknown' not found"):
            storage._resolve_mount("unknown")

    def test_resolve_mount_method_priority(self, tmp_path: Path) -> None:
        """Method has priority over config with same name."""
        storage = LocalStorage(base_dir=tmp_path)
        # Add a configured mount named "site" pointing elsewhere
        other_path = tmp_path / "other"
        other_path.mkdir()
        storage._mounts["site"] = other_path
        # Method should still win
        assert storage._resolve_mount("site") == tmp_path

    def test_has_mount_predefined(self, tmp_path: Path) -> None:
        """has_mount returns True for predefined mount_* methods."""
        storage = LocalStorage(base_dir=tmp_path)
        assert storage.has_mount("site") is True

    def test_has_mount_configured(self, tmp_path: Path) -> None:
        """has_mount returns True for configured mounts."""
        storage = LocalStorage()
        storage.add_mount({"name": "data", "type": "local", "path": str(tmp_path)})
        assert storage.has_mount("data") is True

    def test_has_mount_false(self) -> None:
        """has_mount returns False for unknown mounts."""
        storage = LocalStorage()
        assert storage.has_mount("unknown") is False

    def test_node_uses_resolve_mount_site(self, tmp_path: Path) -> None:
        """node() works with predefined 'site' mount without explicit configuration."""
        storage = LocalStorage(base_dir=tmp_path)
        # Create a test file
        (tmp_path / "resources").mkdir()
        (tmp_path / "resources" / "logo.png").write_bytes(b"\x89PNG")

        node = storage.node("site:resources/logo.png")
        assert node._absolute_path == tmp_path / "resources" / "logo.png"
        assert node.exists is True

    def test_node_site_no_config_needed(self, tmp_path: Path) -> None:
        """'site' mount works without calling add_mount()."""
        storage = LocalStorage(base_dir=tmp_path)
        # No add_mount call, but 'site' should still work
        node = storage.node("site:test.txt")
        assert node.fullpath == "site:test.txt"
        assert node._absolute_path == tmp_path / "test.txt"

    def test_subclass_custom_mount(self, tmp_path: Path) -> None:
        """Subclass can define custom mount_* methods."""

        class CustomStorage(LocalStorage):
            def mount_cache(self) -> Path:
                return self._base_dir / "cache"

        storage = CustomStorage(base_dir=tmp_path)
        assert storage.has_mount("cache") is True
        assert storage._resolve_mount("cache") == tmp_path / "cache"

    def test_children_uses_resolve_mount(self, tmp_path: Path) -> None:
        """children() works with predefined mounts."""
        storage = LocalStorage(base_dir=tmp_path)
        # Create test structure
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")

        node = storage.node("site")
        children = node.children()
        names = [c.basename for c in children]
        assert "file1.txt" in names
        assert "file2.txt" in names
