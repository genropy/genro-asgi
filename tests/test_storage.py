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

"""Tests for LocalStorage (Macro 3 Phase 1): filesystem-only storage, sync API.

Real filesystem, no mocks. Covers mounts (predefined + configured), node
navigation, text/bytes roundtrips, the spool primitives (move_to/remove_tree),
mimetype, and the at-rest encryption contract (ciphertext on disk, key
rotation, and D5 no-silent-degradation explicit errors).
"""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from genro_asgi_core.storage import LocalStorage


@pytest.fixture
def temp_storage(tmp_path: Path) -> LocalStorage:
    """Create a LocalStorage with a temporary 'test' mount."""
    storage = LocalStorage(base_dir=tmp_path)
    storage.add_mount({"name": "test", "type": "local", "path": str(tmp_path)})
    return storage


@pytest.fixture
def temp_storage_with_files(temp_storage: LocalStorage, tmp_path: Path) -> LocalStorage:
    """Create storage with some test files."""
    (tmp_path / "file.txt").write_text("hello")
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "logo.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "style.css").write_text("body { color: red; }")
    return temp_storage


@pytest.fixture
def key() -> str:
    """A single fresh Fernet key."""
    return Fernet.generate_key().decode()


@pytest.fixture
def secure_storage(tmp_path: Path, key: str) -> LocalStorage:
    """Storage with an encrypted 'secure' mount and installed keys."""
    storage = LocalStorage(base_dir=tmp_path)
    storage.set_encryption_keys(key)
    return storage


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

    def test_exists_true(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.exists is True

    def test_exists_false(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:nonexistent.txt")
        assert node.exists is False

    def test_isfile(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.isfile is True
        assert node.isdir is False

    def test_isdir(self, temp_storage_with_files: LocalStorage) -> None:
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

    def test_write_creates_parent_dirs(self, temp_storage: LocalStorage, tmp_path: Path) -> None:
        node = temp_storage.node("test:deep/nested/dir/file.txt")
        node.write_text("nested content")
        assert (tmp_path / "deep" / "nested" / "dir" / "file.txt").exists()

    def test_generic_write_read_text(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:g.txt")
        assert node.write("plain text") is True
        assert node.read() == "plain text"

    def test_generic_write_read_bytes(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:g.bin")
        assert node.write(b"raw bytes", mode="wb") is True
        assert node.read(mode="rb") == b"raw bytes"

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

    def test_children_empty_dir(self, temp_storage: LocalStorage, tmp_path: Path) -> None:
        (tmp_path / "empty_dir").mkdir()
        node = temp_storage.node("test:empty_dir")
        assert node.children() == []

    def test_children_file_returns_empty(self, temp_storage_with_files: LocalStorage) -> None:
        node = temp_storage_with_files.node("test:file.txt")
        assert node.children() == []


class TestLocalStorage:
    """Tests for the LocalStorage manager."""

    def test_add_mount(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.add_mount({"name": "test", "type": "local", "path": str(tmp_path)})
        assert storage.has_mount("test")

    def test_add_mount_relative_path(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        storage.add_mount({"name": "rel", "type": "local", "path": "subdir"})
        assert storage.has_mount("rel")
        assert storage.mounts["rel"] == (tmp_path / "subdir").resolve()

    def test_add_mount_invalid_type(self) -> None:
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
        storage.delete_mount("nonexistent")  # no raise

    def test_get_mount_names(self, tmp_path: Path) -> None:
        storage = LocalStorage()
        storage.add_mount({"name": "a", "type": "local", "path": str(tmp_path)})
        storage.add_mount({"name": "b", "type": "local", "path": str(tmp_path)})
        names = storage.get_mount_names()
        assert "a" in names
        assert "b" in names

    def test_mounts_property_is_live(self, tmp_path: Path) -> None:
        """`mounts` exposes the live configured-mount dict (code → Path)."""
        storage = LocalStorage(base_dir=tmp_path)
        assert storage.mounts == {}
        storage.add_mount({"name": "data", "type": "local", "path": str(tmp_path)})
        assert "data" in storage.mounts
        assert storage.mounts["data"] == Path(tmp_path).resolve()

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
        assert node.fullpath == "test:resources/logo.png"
        assert node.path == "resources/logo.png"

    def test_node_with_parts(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test", "resources", "logo.png")
        assert node.fullpath == "test:resources/logo.png"

    def test_node_mixed_syntax(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:resources", "images", "logo.png")
        assert node.path == "resources/images/logo.png"

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
        """Fallback to configured mounts if a method doesn't exist."""
        storage = LocalStorage()
        storage.add_mount({"name": "data", "type": "local", "path": str(tmp_path)})
        assert storage._resolve_mount("data") == tmp_path

    def test_resolve_mount_not_found(self) -> None:
        """ValueError if mount not found."""
        storage = LocalStorage()
        with pytest.raises(ValueError, match="Mount 'unknown' not found"):
            storage._resolve_mount("unknown")

    def test_resolve_mount_method_priority(self, tmp_path: Path) -> None:
        """Method has priority over config with the same name."""
        storage = LocalStorage(base_dir=tmp_path)
        other_path = tmp_path / "other"
        other_path.mkdir()
        storage.mounts["site"] = other_path
        assert storage._resolve_mount("site") == tmp_path

    def test_has_mount_predefined(self, tmp_path: Path) -> None:
        """has_mount returns True for predefined mount_* methods."""
        storage = LocalStorage(base_dir=tmp_path)
        assert storage.has_mount("site") is True
        assert storage.has_mount("secure") is True

    def test_node_uses_resolve_mount_site(self, tmp_path: Path) -> None:
        """node() works with the predefined 'site' mount without configuration."""
        storage = LocalStorage(base_dir=tmp_path)
        (tmp_path / "resources").mkdir()
        (tmp_path / "resources" / "logo.png").write_bytes(b"\x89PNG")
        node = storage.node("site:resources/logo.png")
        assert node.exists is True

    def test_node_site_no_config_needed(self, tmp_path: Path) -> None:
        """'site' mount works without calling add_mount()."""
        storage = LocalStorage(base_dir=tmp_path)
        node = storage.node("site:test.txt")
        assert node.fullpath == "site:test.txt"

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
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")
        node = storage.node("site")
        names = [c.basename for c in node.children()]
        assert "file1.txt" in names
        assert "file2.txt" in names


class TestMountEscapeGuard:
    """The mount is a security boundary: a path escaping it raises (Phase 10, D5)."""

    def test_read_dotdot_escape_raises(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        (tmp_path.parent / "escape.txt").write_text("outside")
        with pytest.raises(ValueError, match="escapes mount 'site'"):
            storage.node("site:../escape.txt").read_text()

    def test_write_dotdot_escape_raises(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="escapes mount 'site'"):
            storage.node("site:../escape.txt").write_text("nope")

    def test_delete_dotdot_escape_raises(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="escapes mount 'site'"):
            storage.node("site:../escape.txt").delete()

    def test_nested_dotdot_escape_raises(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="escapes mount 'site'"):
            storage.node("site:sub/../../escape.txt").read_text()

    def test_absolute_segment_rejected(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="escapes mount 'site'"):
            storage.node("site:/etc/passwd").read_text()

    def test_dotdot_inside_mount_is_denied_too(self, tmp_path: Path) -> None:
        """Upward navigation is denied even when it resolves inside the mount."""
        storage = LocalStorage(base_dir=tmp_path)
        (tmp_path / "other.txt").write_text("inside")
        with pytest.raises(ValueError, match="escapes mount 'site'"):
            storage.node("site:sub/../other.txt").read_text()

    def test_guard_applies_to_configured_mounts(self, temp_storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="escapes mount 'test'"):
            temp_storage.node("test:../escape.txt").read_text()

    def test_normal_nested_navigation_still_works(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        node = storage.node("site:sub/child.txt")
        assert node.write_text("fine") is True
        assert node.read_text() == "fine"

    def test_child_and_children_navigation_still_works(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        parent = storage.node("site:sub")
        parent.child("a.txt").write_text("a")
        parent.child("b.txt").write_text("b")
        names = sorted(c.basename for c in parent.children())
        assert names == ["a.txt", "b.txt"]
        assert parent.child("a.txt").parent.path == "sub"


class TestNodeDelete:
    """LocalStorageNode.delete() on a plain (unencrypted) mount."""

    def test_delete_existing_file_returns_true(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:gone.txt")
        node.write_text("bye")
        assert node.exists is True
        assert node.delete() is True
        assert node.exists is False

    def test_delete_absent_file_returns_false(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:never.txt")
        assert node.exists is False
        assert node.delete() is False

    def test_delete_directory_is_error(self, temp_storage_with_files: LocalStorage) -> None:
        """delete() targets files only: a directory raises explicitly."""
        node = temp_storage_with_files.node("test:images")
        assert node.isdir is True
        with pytest.raises(IsADirectoryError):
            node.delete()


class TestNodeMoveAndTree:
    """LocalStorageNode.move_to() and remove_tree() — the spool primitives."""

    def test_move_file_relocates_content(self, temp_storage: LocalStorage) -> None:
        src = temp_storage.node("test:src.txt")
        src.write_text("payload")
        dest = temp_storage.node("test:moved/dst.txt")
        assert src.move_to(dest) is True
        assert src.exists is False
        assert dest.exists is True
        assert dest.read_text() == "payload"

    def test_move_directory_with_children(self, temp_storage: LocalStorage) -> None:
        temp_storage.node("test:pending/task1/descriptor.json").write_text('{"id":"task1"}')
        temp_storage.node("test:pending/task1/params.pkl").write_bytes(b"data")
        temp_storage.node("test:pending/task1").move_to(
            temp_storage.node("test:active/w1/task1")
        )
        assert temp_storage.node("test:pending/task1").exists is False
        assert temp_storage.node("test:active/w1/task1").isdir is True
        assert (
            temp_storage.node("test:active/w1/task1/descriptor.json").read_text()
            == '{"id":"task1"}'
        )
        assert temp_storage.node("test:active/w1/task1/params.pkl").exists is True

    def test_move_absent_source_raises(self, temp_storage: LocalStorage) -> None:
        with pytest.raises(FileNotFoundError):
            temp_storage.node("test:nope").move_to(temp_storage.node("test:elsewhere"))

    def test_remove_tree_directory(self, temp_storage: LocalStorage) -> None:
        temp_storage.node("test:job/a/b.txt").write_text("x")
        node = temp_storage.node("test:job")
        assert node.isdir is True
        assert node.remove_tree() is True
        assert node.exists is False

    def test_remove_tree_file(self, temp_storage: LocalStorage) -> None:
        node = temp_storage.node("test:single.txt")
        node.write_text("x")
        assert node.remove_tree() is True
        assert node.exists is False

    def test_remove_tree_absent_returns_false(self, temp_storage: LocalStorage) -> None:
        assert temp_storage.node("test:ghost").remove_tree() is False


class TestEncryptionState:
    """set_encryption_keys / encryption_active."""

    def test_inactive_by_default(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        assert storage.encryption_active is False

    def test_active_after_install(self, tmp_path: Path, key: str) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        storage.set_encryption_keys(key)
        assert storage.encryption_active is True

    def test_empty_keys_rejected(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        with pytest.raises(ValueError):
            storage.set_encryption_keys("   ")

    def test_multiple_keys_installed(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        a, b = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        storage.set_encryption_keys(f"{a}, {b}")
        assert storage.encryption_active is True


class TestSecureMountRoundtrip:
    """Transparent encrypt-on-write / decrypt-on-read for the secure mount."""

    def test_text_roundtrip(self, secure_storage: LocalStorage) -> None:
        node = secure_storage.node("secure:doc.txt")
        assert node.write_text("hello secret") is True
        assert node.read_text() == "hello secret"

    def test_bytes_roundtrip(self, secure_storage: LocalStorage) -> None:
        node = secure_storage.node("secure:blob.bin")
        payload = b"\x00\x01\x02binary secret\xff"
        assert node.write_bytes(payload) is True
        assert node.read_bytes() == payload

    def test_disk_is_ciphertext(self, secure_storage: LocalStorage, tmp_path: Path) -> None:
        node = secure_storage.node("secure:onwire.txt")
        secret = "TOP-SECRET-MARKER"
        node.write_text(secret)
        raw = (tmp_path / "secure" / "onwire.txt").read_bytes()
        assert secret.encode() not in raw
        assert raw != secret.encode()

    def test_delete_removes_the_encrypted_file(
        self, secure_storage: LocalStorage, tmp_path: Path
    ) -> None:
        """delete() removes a ciphertext file on an encrypted mount as on a plain one."""
        node = secure_storage.node("secure:doomed.txt")
        node.write_text("erase me")
        assert (tmp_path / "secure" / "doomed.txt").exists()
        assert node.delete() is True
        assert not (tmp_path / "secure" / "doomed.txt").exists()
        assert node.delete() is False


class TestConfiguredEncryptedMount:
    """A mount declared encrypted: True in add_mount behaves like secure."""

    def test_encrypted_mount_roundtrip(self, tmp_path: Path, key: str) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        storage.set_encryption_keys(key)
        storage.add_mount(
            {"name": "vault", "type": "local", "path": "vault", "encrypted": True}
        )
        node = storage.node("vault:secret.txt")
        node.write_text("vault content")
        assert node.read_text() == "vault content"
        raw = (tmp_path / "vault" / "secret.txt").read_bytes()
        assert b"vault content" not in raw


class TestPlainMountUnchanged:
    """Non-encrypted mounts keep plain behavior exactly."""

    def test_plain_roundtrip_and_readable_on_disk(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        storage.add_mount({"name": "plain", "type": "local", "path": "plain"})
        node = storage.node("plain:note.txt")
        node.write_text("readable")
        assert node.read_text() == "readable"
        raw = (tmp_path / "plain" / "note.txt").read_bytes()
        assert raw == b"readable"

    def test_plain_unaffected_by_installed_keys(self, tmp_path: Path, key: str) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        storage.set_encryption_keys(key)
        storage.add_mount({"name": "plain", "type": "local", "path": "plain"})
        node = storage.node("plain:note.txt")
        node.write_text("still plain")
        raw = (tmp_path / "plain" / "note.txt").read_bytes()
        assert raw == b"still plain"


class TestNoSilentDegradation:
    """D5: explicit errors, never a plain-text fallback."""

    def test_secure_without_keys_raises_on_write(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        node = storage.node("secure:x.txt")
        with pytest.raises(RuntimeError):
            node.write_text("nope")

    def test_secure_without_keys_raises_on_read(self, tmp_path: Path, key: str) -> None:
        # Write with keys, then a fresh storage without keys must refuse to read.
        writer = LocalStorage(base_dir=tmp_path)
        writer.set_encryption_keys(key)
        writer.node("secure:x.txt").write_text("secret")
        reader = LocalStorage(base_dir=tmp_path)
        with pytest.raises(RuntimeError):
            reader.node("secure:x.txt").read_text()

    def test_non_fernet_payload_raises_on_read(
        self, secure_storage: LocalStorage, tmp_path: Path
    ) -> None:
        # Plant a plain (non-Fernet) file on the encrypted mount, then read.
        secure_dir = tmp_path / "secure"
        secure_dir.mkdir(parents=True, exist_ok=True)
        (secure_dir / "corrupt.txt").write_bytes(b"not a fernet token")
        with pytest.raises(InvalidToken):
            secure_storage.node("secure:corrupt.txt").read_text()

    def test_encrypted_mount_config_without_keys_raises(self, tmp_path: Path) -> None:
        storage = LocalStorage(base_dir=tmp_path)
        storage.add_mount(
            {"name": "vault", "type": "local", "path": "vault", "encrypted": True}
        )
        with pytest.raises(RuntimeError):
            storage.node("vault:x.txt").write_text("nope")


class TestKeyRotation:
    """MultiFernet: first key encrypts, all keys decrypt."""

    def test_rotation_reads_old_and_reencrypts_new(self, tmp_path: Path) -> None:
        a = Fernet.generate_key().decode()
        b = Fernet.generate_key().decode()

        # Write with A installed.
        s1 = LocalStorage(base_dir=tmp_path)
        s1.set_encryption_keys(a)
        s1.node("secure:rot.txt").write_text("v1")

        # Re-install as "B,A": B encrypts, A still decrypts the old file.
        s2 = LocalStorage(base_dir=tmp_path)
        s2.set_encryption_keys(f"{b},{a}")
        assert s2.node("secure:rot.txt").read_text() == "v1"

        # A new write is encrypted with the FIRST key (B): A alone cannot read it.
        s2.node("secure:new.txt").write_text("v2")
        raw = (tmp_path / "secure" / "new.txt").read_bytes()
        with pytest.raises(InvalidToken):
            Fernet(a).decrypt(raw)
        assert Fernet(b).decrypt(raw).decode() == "v2"
