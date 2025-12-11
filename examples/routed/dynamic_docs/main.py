#!/usr/bin/env python
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
Genro modules documentation server.

DocsServer subclasses AsgiServer to serve documentation for genro-* modules.

Structure:
    /                           → Redirect to /docs/
    /docs/                      → Dynamic index (list of modules)
    /docs/<module>/docs/        → Sphinx docs
    /docs/<module>/examples/    → Examples
    /docs/<module>/info         → Module info JSON
    /_sys/sites                 → List active sites
    /_sys/add                   → Add site dynamically
    /_sys/remove                → Remove site
    /_sys/routes                → Router introspection

Run with:
    python main.py
    python main.py --port 9000
    python main.py --modules-dir /path/to/modules
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from genro_asgi import AsgiServer, RedirectResponse
from genro_routes import route
from genro_toolbox import MultiDefault, SmartOptions

from app import Docs, SysApi


DEFAULTS = {
    "server_host": "127.0.0.1",
    "server_port": 8090,
    "server_debug": True,
    "app_modulesdir": "../../..",  # relative to config file
}

CONFIG_TYPES = {
    "server_port": int,
    "server_debug": bool,
}


class DocsServer(AsgiServer):
    """
    Documentation server for genro modules.

    Subclasses AsgiServer to provide:
    - /docs/ with module listing and per-module docs
    - /_sys/ with server management API
    - / redirect to /docs/
    """

    def __init__(self, modules_dir: Path, **kwargs):
        super().__init__(use_router=True, **kwargs)

        # Docs at /docs/
        self.docs = Docs(modules_dir=modules_dir)
        self.router.attach_instance(self.docs, name="docs")

        # SysApi at /_sys/
        self._sys = SysApi(server=self)
        self.router.attach_instance(self._sys, name="_sys")

    @route("root")
    def index(self) -> RedirectResponse:
        """Redirect root to /docs/."""
        return RedirectResponse("/docs/")


def configure() -> SmartOptions:
    """Load configuration from defaults, config file, env vars, and CLI."""
    parser = argparse.ArgumentParser(description="Genro modules documentation server")
    parser.add_argument("--config", "-c", type=Path, help="Config file")
    parser.add_argument("--host", type=str, help="Server host")
    parser.add_argument("--port", "-p", type=int, help="Server port")
    parser.add_argument("--modules-dir", "-m", type=Path, help="Modules directory")
    args = parser.parse_args()

    # Find config file
    config_path = args.config
    if config_path is None:
        config_path = Path(__file__).parent / "genro-asgi.toml"

    # Load config from multiple sources
    sources = [DEFAULTS]
    if config_path.exists():
        sources.append(str(config_path))
    sources.append("ENV:GENRO_ASGI")

    defaults = MultiDefault(*sources, skip_missing=True, types=CONFIG_TYPES)

    # CLI overrides
    cli_overrides = {}
    if args.host:
        cli_overrides["server_host"] = args.host
    if args.port:
        cli_overrides["server_port"] = args.port
    if args.modules_dir:
        cli_overrides["app_modulesdir"] = str(args.modules_dir)

    opts = SmartOptions(incoming=cli_overrides, defaults=defaults, ignore_none=True)

    # Resolve modules dir relative to config file
    base_path = config_path.parent if config_path.exists() else Path.cwd()
    opts.modules_dir = (base_path / opts.app_modulesdir).resolve()

    return opts


def main() -> int:
    opts = configure()
    server = DocsServer(modules_dir=opts.modules_dir)
    server.run(host=str(opts.server_host), port=int(opts.server_port))
    return 0


if __name__ == "__main__":
    sys.exit(main())
