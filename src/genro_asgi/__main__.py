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
genro-asgi CLI entry point.

Usage:
    genro-asgi serve config.toml              # Run server with config
    genro-asgi serve config.toml --port 9000  # Override port
    genro-asgi serve --show-config            # Show loaded configuration

Configuration Priority (lowest to highest):
    1. Hardcoded defaults
    2. Config file (TOML)
    3. Environment variables (GENRO_ASGI_*)
    4. CLI arguments

Environment Variables:
    GENRO_ASGI_SERVER_HOST     Override server host
    GENRO_ASGI_SERVER_PORT     Override server port
    GENRO_ASGI_SERVER_DEBUG    Enable debug mode (true/false)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from genro_toolbox import MultiDefault, SmartOptions, dictExtract

if TYPE_CHECKING:
    from .server import AsgiServer

# Default configuration values (flat keys)
DEFAULTS = {
    "server_host": "127.0.0.1",
    "server_port": 8000,
    "server_debug": False,
    "server_loglevel": "info",
    "server_reload": False,
}

# Type conversions for config values
CONFIG_TYPES = {
    "server_port": int,
    "server_debug": bool,
    "server_reload": bool,
}


def extract_staticsites(config: dict[str, object]) -> dict[str, dict[str, object]]:
    """
    Extract static sites configuration from flattened config.

    Flattened keys like:
        staticsites_landing_path = "/"
        staticsites_landing_directory = "./public"
        staticsites_storage_path = "/storage"

    Become:
        {
            "landing": {"path": "/", "directory": "./public"},
            "storage": {"path": "/storage"}
        }

    Args:
        config: Flattened configuration dict.

    Returns:
        Dict of site_name -> site_config.
    """
    sites: dict[str, dict[str, object]] = {}

    # Extract all staticsites_* keys
    prefix = "staticsites_"
    for key, value in config.items():
        if not key.startswith(prefix):
            continue

        # Remove prefix: "staticsites_landing_path" -> "landing_path"
        rest = key[len(prefix):]

        # Split on first underscore: "landing_path" -> ("landing", "path")
        if "_" not in rest:
            continue

        site_name, param = rest.split("_", 1)

        if site_name not in sites:
            sites[site_name] = {}

        sites[site_name][param] = value

    return sites


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for genro-asgi CLI."""
    parser = argparse.ArgumentParser(
        prog="genro-asgi",
        description="genro-asgi - Minimal ASGI server",
    )

    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version and exit",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # serve command
    serve_parser = subparsers.add_parser(
        "serve",
        help="Run the ASGI server",
        description="Start the ASGI server with the specified configuration",
    )

    serve_parser.add_argument(
        "config",
        type=Path,
        nargs="?",
        help="Path to configuration file (TOML)",
    )

    serve_parser.add_argument(
        "--host",
        type=str,
        help="Override server host",
    )

    serve_parser.add_argument(
        "--port", "-p",
        type=int,
        help="Override server port",
    )

    serve_parser.add_argument(
        "--reload", "-r",
        action="store_true",
        default=None,
        help="Enable auto-reload (development mode)",
    )

    serve_parser.add_argument(
        "--debug", "-d",
        action="store_true",
        default=None,
        help="Enable debug mode",
    )

    serve_parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show loaded configuration and exit",
    )

    return parser


def load_configuration(
    config_path: Path | None,
    cli_overrides: dict[str, object],
) -> SmartOptions:
    """
    Load configuration from multiple sources with priority.

    Priority (lowest to highest):
        1. DEFAULTS (hardcoded)
        2. config_path (TOML file)
        3. ENV:GENRO_ASGI (environment variables)
        4. cli_overrides (command line arguments)

    Args:
        config_path: Path to TOML configuration file (optional).
        cli_overrides: CLI argument overrides.

    Returns:
        SmartOptions with merged configuration.
    """
    sources: list[object] = [DEFAULTS]

    if config_path and config_path.exists():
        sources.append(str(config_path))

    sources.append("ENV:GENRO_ASGI")

    defaults = MultiDefault(
        *sources,
        skip_missing=True,
        types=CONFIG_TYPES,
    )

    return SmartOptions(
        incoming=cli_overrides,
        defaults=defaults,
        ignore_none=True,
    )


def find_config_file() -> Path | None:
    """
    Find configuration file in current directory.

    Looks for: genro-asgi.toml, config.toml

    Returns:
        Path to config file or None if not found.
    """
    cwd = Path.cwd()
    candidates = ["genro-asgi.toml", "config.toml"]

    for name in candidates:
        path = cwd / name
        if path.exists():
            return path

    return None


def create_server_from_opts(opts: SmartOptions, base_path: Path) -> "AsgiServer":
    """
    Create AsgiServer from configuration options.

    Args:
        opts: SmartOptions with flattened configuration.
        base_path: Base path for resolving relative paths.

    Returns:
        Configured AsgiServer instance.
    """
    from .server import AsgiServer
    from .static import StaticFiles

    server = AsgiServer()

    # Get the flattened config dict
    config_dict = opts.as_dict()

    # Extract static sites from flattened config
    # staticsites_<name>_<param> -> {name: {param: value}}
    sites = extract_staticsites(config_dict)

    for site_name, site_config in sites.items():
        url_path = site_config.get("path")
        directory = site_config.get("directory")

        if not url_path or not directory:
            print(f"Warning: staticsites.{site_name} missing path or directory")
            continue

        full_path = (base_path / str(directory)).resolve()

        # Get optional parameters
        index = site_config.get("index", "index.html")
        fallback = site_config.get("fallback")

        app = StaticFiles(
            directory=full_path,
            index=str(index) if index else "index.html",
            fallback=str(fallback) if fallback else None,
        )
        server.mount(str(url_path), app)

    return server


def cmd_serve(args: argparse.Namespace) -> int:
    """
    Execute the 'serve' command.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    # Find config file
    config_path = args.config
    if config_path is None:
        config_path = find_config_file()

    if config_path is None:
        print("Error: No configuration file specified or found.", file=sys.stderr)
        print("Usage: genro-asgi serve <config.toml>", file=sys.stderr)
        print("Or create genro-asgi.toml in current directory", file=sys.stderr)
        return 1

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        return 1

    # Build CLI overrides dict
    cli_overrides: dict[str, object] = {}
    if args.host is not None:
        cli_overrides["server_host"] = args.host
    if args.port is not None:
        cli_overrides["server_port"] = args.port
    if args.reload is not None:
        cli_overrides["server_reload"] = args.reload
    if args.debug is not None:
        cli_overrides["server_debug"] = args.debug

    # Load configuration
    try:
        opts = load_configuration(config_path, cli_overrides)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Show config and exit
    if args.show_config:
        import json
        print(f"Configuration file: {config_path}")
        print("Environment prefix: GENRO_ASGI_*")
        print()
        print("Resolved configuration:")
        print(json.dumps(opts.as_dict(), indent=2, default=str))
        return 0

    # Create server
    try:
        base_path = config_path.parent
        server = create_server_from_opts(opts, base_path)
    except Exception as e:
        print(f"Error creating server: {e}", file=sys.stderr)
        return 1

    # Get server settings
    server_opts = dictExtract(opts.as_dict(), "server_")
    host = server_opts.get("host", "127.0.0.1")
    port = server_opts.get("port", 8000)
    reload = server_opts.get("reload", False)

    # Show startup info
    print("genro-asgi starting...")
    print(f"Config: {config_path}")
    print(f"Server: http://{host}:{port}")

    if reload:
        print("Mode: development (auto-reload enabled)")

    # Show mounts
    if server.apps:
        print("Mounts:")
        for mount_path in sorted(server.apps.keys()):
            app_info = server.apps[mount_path]
            app = app_info["app"]
            app_type = type(app).__name__
            print(f"  {mount_path} -> {app_type}")

    print()

    # Run server
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nShutdown.")
        return 0

    return 0


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for genro-asgi CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success).
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Version
    if args.version:
        from . import __version__
        print(f"genro-asgi {__version__}")
        return 0

    # No command specified
    if args.command is None:
        parser.print_help()
        return 0

    # Dispatch to command handler
    if args.command == "serve":
        return cmd_serve(args)

    # Unknown command (shouldn't happen with subparsers)
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
