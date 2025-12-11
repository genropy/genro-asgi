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

"""
Configuration utilities for genro-asgi.

This module provides helpers for configuration loading. The main configuration
system uses genro-toolbox MultiDefault for multi-source config with priority:

    hardcoded defaults < TOML file < environment variables < CLI arguments

Key constraints:
- TOML keys CANNOT contain underscore (_) as it's used as the flattening separator
- Environment variables use prefix GENRO_ASGI_ (e.g., GENRO_ASGI_SERVER_PORT)

Example TOML structure:
    [server]
    host = "127.0.0.1"
    port = 8080

    [staticsites.landing]
    path = "/"
    directory = "./public"
    index = "index.html"

This becomes flattened to:
    server_host = "127.0.0.1"
    server_port = 8080
    staticsites_landing_path = "/"
    staticsites_landing_directory = "./public"
    staticsites_landing_index = "index.html"
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

# Python 3.11+ has tomllib in stdlib
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

__all__ = ["load_config", "find_config_file", "ConfigError", "validate_keys"]


class ConfigError(Exception):
    """Configuration error."""


def validate_keys(data: Any, path: str = "") -> None:
    """
    Validate that no keys contain underscore.

    Args:
        data: Configuration data (dict, list, or value).
        path: Current path for error messages.

    Raises:
        ConfigError: If a key contains underscore.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if "_" in key:
                full_path = f"{path}.{key}" if path else key
                raise ConfigError(
                    f"Invalid key '{full_path}': underscore (_) is not allowed in keys. "
                    f"Use camelCase or single words instead."
                )
            child_path = f"{path}.{key}" if path else key
            validate_keys(value, child_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            validate_keys(item, f"{path}[{i}]")


def load_config(path: str | Path) -> dict[str, Any]:
    """
    Load configuration from TOML file.

    Args:
        path: Path to TOML configuration file.

    Returns:
        Parsed configuration dict.

    Raises:
        ConfigError: If file not found, invalid TOML, or keys contain underscore.
    """
    if tomllib is None:
        raise ConfigError(
            "TOML support requires Python 3.11+ or 'tomli' package. "
            "Install with: pip install tomli"
        )

    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        with open(path, "rb") as f:
            config = tomllib.load(f)
    except Exception as e:
        raise ConfigError(f"Failed to parse TOML: {e}") from e

    # Validate no underscore in keys
    validate_keys(config)

    # Expand environment variables
    config = _expand_env_vars(config)

    return dict(config)


def _expand_env_vars(obj: Any) -> Any:
    """
    Recursively expand environment variables in config values.

    Supports:
    - ${VAR} - required, raises if not set
    - ${VAR:-default} - with default value

    Args:
        obj: Config object (dict, list, or value).

    Returns:
        Object with environment variables expanded.
    """
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        return _expand_string(obj)
    return obj


def _expand_string(s: str) -> str:
    """
    Expand environment variables in a string.

    Args:
        s: String potentially containing ${VAR} or ${VAR:-default}.

    Returns:
        String with variables expanded.

    Raises:
        ConfigError: If required variable is not set.
    """
    pattern = r"\$\{([^}]+)\}"

    def replace(match: re.Match[str]) -> str:
        expr = match.group(1)

        # Check for default value
        if ":-" in expr:
            var_name, default = expr.split(":-", 1)
            return os.environ.get(var_name, default)
        else:
            value = os.environ.get(expr)
            if value is None:
                raise ConfigError(f"Required environment variable not set: {expr}")
            return value

    return re.sub(pattern, replace, s)


def find_config_file() -> Path | None:
    """
    Find configuration file in standard locations.

    Searches:
    1. GENRO_ASGI_CONFIG environment variable
    2. ./genro-asgi.toml
    3. ./config.toml
    4. ./config/genro-asgi.toml
    5. ~/.config/genro-asgi/config.toml

    Returns:
        Path to config file or None if not found.
    """
    # Check GENRO_ASGI_CONFIG env var first
    env_config = os.environ.get("GENRO_ASGI_CONFIG")
    if env_config:
        path = Path(env_config)
        if path.exists():
            return path

    locations = [
        Path.cwd() / "genro-asgi.toml",
        Path.cwd() / "config.toml",
        Path.cwd() / "config" / "genro-asgi.toml",
        Path.home() / ".config" / "genro-asgi" / "config.toml",
    ]

    for path in locations:
        if path.exists():
            return path

    return None


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Load and validate config")
    parser.add_argument("config", nargs="?", help="Config file path")
    parser.add_argument("--show", action="store_true", help="Show parsed config")
    args = parser.parse_args()

    config_path: Path | None
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = find_config_file()

    if config_path is None:
        print("No configuration file found")
        sys.exit(1)

    print(f"Loading: {config_path}")

    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if args.show:
        print(json.dumps(config, indent=2, default=str))
