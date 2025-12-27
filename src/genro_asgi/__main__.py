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
    genro-asgi serve ./myapp              # Run server from app directory
    genro-asgi serve ./myapp --port 9000  # Override port

The directory must contain a config.yaml or genro-asgi.yaml file.
"""

from __future__ import annotations

import sys


def cmd_serve(argv: list[str]) -> int:
    """Run the ASGI server."""
    from .server import AsgiServer

    # Create server - passes argv for SmartOptions parsing
    server = AsgiServer(argv=argv)

    # Verify server_dir exists
    server_dir = server.config.server["server_dir"]
    if not server_dir.is_dir():
        print(f"Error: '{server_dir}' is not a directory.", file=sys.stderr)
        return 1

    # Show startup info
    print("genro-asgi starting...", flush=True)
    print(f"Server dir: {server_dir}", flush=True)
    print(f"Server: http://{server.config.server['host']}:{server.config.server['port']}", flush=True)
    if server.config.server["reload"]:
        print("Mode: development (auto-reload enabled)", flush=True)
    print(flush=True)

    # Run server
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nShutdown.")

    return 0


def main() -> int:
    """Main entry point."""
    # Handle --version
    if "--version" in sys.argv or "-v" in sys.argv:
        from . import __version__

        print(f"genro-asgi {__version__}")
        return 0

    # Handle --help
    if "--help" in sys.argv or "-h" in sys.argv or len(sys.argv) == 1:
        print("Usage: genro-asgi serve <app_dir> [options]")
        print()
        print("Arguments:")
        print("  app_dir           Path to app directory")
        print()
        print("Options:")
        print("  --host HOST       Server host (default: 127.0.0.1)")
        print("  --port PORT       Server port (default: 8000)")
        print("  --reload          Enable auto-reload")
        print("  --version, -v     Show version")
        print("  --help, -h        Show this help")
        return 0

    # Extract subcommand
    if len(sys.argv) < 2:
        print("Error: missing subcommand", file=sys.stderr)
        return 1

    subcommand = sys.argv[1]
    if subcommand != "serve":
        print(f"Error: unknown subcommand '{subcommand}'", file=sys.stderr)
        return 1

    return cmd_serve(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
