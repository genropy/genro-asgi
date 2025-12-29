# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""AppLoader - Isolated module loading with virtual namespace.

Loads app modules into a virtual namespace (genro_root.apps.<name>) to avoid
collisions in sys.path. Each app gets its own isolated namespace.

Usage:
    loader = AppLoader()  # default prefix: "genro_root"

    # Load an app package
    module = loader.load_package("shop", Path("/apps/shop"))
    # Registered as: genro_root.apps.shop

    # The app can now use relative imports:
    # from .sql import Table  → genro_root.apps.shop.sql
    # from .tables import Article → genro_root.apps.shop.tables

    # Cleanup when server stops
    loader.unload_all()

Namespace structure:
    genro_root                    # Root namespace module
    genro_root.apps               # Apps container module
    genro_root.apps.shop          # App package
    genro_root.apps.shop.sql      # Submodule
    genro_root.apps.shop.tables   # Submodule
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

__all__ = ["AppLoader"]

# Directories to skip during recursive submodule loading
IGNORE_DIRS = frozenset({
    "__pycache__", ".git", ".svn", ".hg",
    "venv", ".venv", "env", ".env",
    "node_modules", ".tox", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build",
    ".eggs", "*.egg-info", "tests", "test",
})


class AppLoader:
    """Loads app modules into isolated virtual namespace.

    Avoids sys.path pollution by registering modules with unique names
    in sys.modules. Each app gets namespace: {prefix}.apps.{app_name}

    Args:
        prefix: Root namespace prefix (default: "genro_root" to avoid collisions)
    """

    __slots__ = ("prefix", "_loaded_modules")

    def __init__(self, prefix: str = "genro_root") -> None:
        self.prefix = prefix
        self._loaded_modules: list[str] = []
        self._ensure_namespace()

    def _ensure_namespace(self) -> None:
        """Create root namespace modules if they don't exist."""
        # Create "server" module
        if self.prefix not in sys.modules:
            root = ModuleType(self.prefix)
            root.__path__ = []  # Make it a package
            sys.modules[self.prefix] = root
            self._loaded_modules.append(self.prefix)

        # Create "server.apps" module
        apps_name = f"{self.prefix}.apps"
        if apps_name not in sys.modules:
            apps = ModuleType(apps_name)
            apps.__path__ = []  # Make it a package
            sys.modules[apps_name] = apps
            # Attach to parent
            setattr(sys.modules[self.prefix], "apps", apps)
            self._loaded_modules.append(apps_name)

    def load_package(self, app_name: str, app_path: Path) -> ModuleType:
        """Load an app package into the virtual namespace.

        Args:
            app_name: Name of the app (e.g., "shop")
            app_path: Path to the app directory

        Returns:
            The loaded module

        Example:
            loader.load_package("shop", Path("/apps/shop"))
            # Creates: server.apps.shop
        """
        full_name = f"{self.prefix}.apps.{app_name}"

        # Check if __init__.py exists (it's a package)
        init_file = app_path / "__init__.py"
        if init_file.exists():
            module = self._load_module(full_name, init_file, is_package=True, package_path=app_path)
        else:
            # No __init__.py - create empty package module
            module = ModuleType(full_name)
            module.__path__ = [str(app_path)]
            module.__file__ = str(app_path)
            sys.modules[full_name] = module
            self._loaded_modules.append(full_name)

        # Attach to parent
        setattr(sys.modules[f"{self.prefix}.apps"], app_name, module)

        # Pre-load submodules (directories with __init__.py and .py files)
        self._load_submodules(full_name, app_path)

        return module

    def _load_submodules(self, parent_name: str, parent_path: Path) -> None:
        """Recursively load submodules of a package."""
        if not parent_path.is_dir():
            return

        for item in parent_path.iterdir():
            # Skip private/special and ignored directories
            if item.name.startswith("_") and item.name != "__init__.py":
                continue
            if item.name in IGNORE_DIRS:
                continue

            if item.is_dir():
                # Check if it's a package (has __init__.py)
                init_file = item / "__init__.py"
                if init_file.exists():
                    submodule_name = f"{parent_name}.{item.name}"
                    self._load_module(submodule_name, init_file, is_package=True, package_path=item)
                    # Recursively load its submodules
                    self._load_submodules(submodule_name, item)

            elif item.suffix == ".py" and item.name != "__init__.py":
                # Regular Python file
                module_name = item.stem
                full_name = f"{parent_name}.{module_name}"
                self._load_module(full_name, item, is_package=False)

    def _load_module(
        self,
        full_name: str,
        file_path: Path,
        is_package: bool = False,
        package_path: Path | None = None
    ) -> ModuleType:
        """Load a single module file.

        Args:
            full_name: Full module name (e.g., "server.apps.shop.sql")
            file_path: Path to the .py file
            is_package: Whether this is a package (__init__.py)
            package_path: Directory path if it's a package

        Returns:
            The loaded module
        """
        # Skip if already loaded
        if full_name in sys.modules:
            return sys.modules[full_name]

        spec = importlib.util.spec_from_file_location(
            full_name,
            file_path,
            submodule_search_locations=[str(package_path)] if is_package and package_path else None
        )

        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module {full_name} from {file_path}")

        module = importlib.util.module_from_spec(spec)

        # Set package info for relative imports
        if is_package:
            module.__path__ = [str(package_path)] if package_path else []
            module.__package__ = full_name
        else:
            # For non-package modules, __package__ is the parent
            module.__package__ = full_name.rsplit(".", 1)[0]

        # Register before executing (allows circular imports)
        sys.modules[full_name] = module
        self._loaded_modules.append(full_name)

        # Attach to parent module
        parent_name = full_name.rsplit(".", 1)[0]
        if parent_name in sys.modules:
            attr_name = full_name.rsplit(".", 1)[1]
            setattr(sys.modules[parent_name], attr_name, module)

        # Execute module code
        spec.loader.exec_module(module)

        return module

    def load_module_from_path(self, app_name: str, module_path: str, file_path: Path) -> ModuleType:
        """Load a specific module file.

        Args:
            app_name: App name (e.g., "shop")
            module_path: Relative module path (e.g., "tables.article")
            file_path: Absolute path to the .py file

        Returns:
            The loaded module
        """
        full_name = f"{self.prefix}.apps.{app_name}.{module_path}"
        return self._load_module(full_name, file_path, is_package=False)

    def get_module(self, app_name: str, module_path: str = "") -> ModuleType | None:
        """Get a loaded module by name.

        Args:
            app_name: App name
            module_path: Optional submodule path

        Returns:
            The module or None if not found
        """
        if module_path:
            full_name = f"{self.prefix}.apps.{app_name}.{module_path}"
        else:
            full_name = f"{self.prefix}.apps.{app_name}"
        return sys.modules.get(full_name)

    def unload_app(self, app_name: str) -> None:
        """Unload all modules for an app.

        Args:
            app_name: App name to unload
        """
        prefix = f"{self.prefix}.apps.{app_name}"
        to_remove = [name for name in self._loaded_modules if name.startswith(prefix)]

        for name in reversed(to_remove):  # Reverse to unload children first
            if name in sys.modules:
                del sys.modules[name]
            self._loaded_modules.remove(name)

        # Remove from parent
        apps_module = sys.modules.get(f"{self.prefix}.apps")
        if apps_module and hasattr(apps_module, app_name):
            delattr(apps_module, app_name)

    def unload_all(self) -> None:
        """Unload all modules loaded by this loader."""
        # Also find any modules that were loaded as side effects
        prefix = f"{self.prefix}."
        all_to_remove = [
            name for name in sys.modules
            if name == self.prefix or name.startswith(prefix)
        ]
        for name in reversed(sorted(all_to_remove)):
            if name in sys.modules:
                del sys.modules[name]
        self._loaded_modules.clear()

    def list_loaded(self) -> list[str]:
        """List all loaded module names."""
        return list(self._loaded_modules)


if __name__ == "__main__":
    # Simple test
    import tempfile

    # Create a temp app structure
    with tempfile.TemporaryDirectory() as tmpdir:
        app_dir = Path(tmpdir) / "test_app"
        app_dir.mkdir()

        # Create __init__.py
        (app_dir / "__init__.py").write_text('APP_NAME = "test"')

        # Create utils.py
        (app_dir / "utils.py").write_text('def helper(): return "hello"')

        # Create subpackage
        sub_dir = app_dir / "models"
        sub_dir.mkdir()
        (sub_dir / "__init__.py").write_text('from .user import User')
        (sub_dir / "user.py").write_text('class User: pass')

        # Test loader with default prefix
        loader = AppLoader()  # uses "genro_root"
        loader.load_package("test_app", app_dir)

        print("Loaded modules:")
        for name in loader.list_loaded():
            print(f"  {name}")

        # Test imports work
        import genro_root.apps.test_app as app
        print(f"\nAPP_NAME: {app.APP_NAME}")

        import genro_root.apps.test_app.utils as utils
        print(f"helper(): {utils.helper()}")

        import genro_root.apps.test_app.models as models
        print(f"User class: {models.User}")

        # Cleanup
        loader.unload_all()
        print("\nAfter unload, modules remaining:",
              [k for k in sys.modules if k.startswith("genro_root")])
