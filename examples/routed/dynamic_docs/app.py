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
Genro modules documentation server using genro_routes.

This example demonstrates:
- Dynamic discovery of genro modules
- Hierarchical routing with genro_routes
- Live server management via _sys API

Structure:
    /                           → Redirect to /docs/
    /docs/                      → Dynamic index (list of modules)
    /docs/<module>/docs/        → Sphinx docs (if available)
    /docs/<module>/examples/    → Examples (if available)
    /docs/<module>/info         → Module info JSON
    /_sys/sites                 → List active sites
    /_sys/add                   → Add site dynamically
    /_sys/remove                → Remove site
    /_sys/routes                → Router introspection
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from genro_routes import Router, RoutingClass, route

from genro_asgi import AsgiServer, StaticSite, HTMLResponse, RedirectResponse


# -----------------------------------------------------------------------------
# ModuleSite: represents a single genro module with its resources
# -----------------------------------------------------------------------------

class ModuleSite(RoutingClass):
    """
    A genro module site with docs and examples.

    Each module can expose:
    - docs: Sphinx documentation (if docs/_build/html exists)
    - examples: Example code (if examples/ exists)
    - info: JSON with module information
    """

    def __init__(self, module_path: Path):
        self.module_path = module_path
        self.name = module_path.name
        self.docs_path = module_path / "docs" / "_build" / "html"
        self.examples_path = module_path / "examples"

        # Check what's available
        self.has_docs = self.docs_path.exists()
        self.has_examples = self.examples_path.exists()

        # Create router with self as owner
        self.router = Router(self, name="api")

    @route("api")
    def docs(self) -> StaticSite | dict[str, str]:
        """Sphinx documentation for this module."""
        if self.has_docs:
            return StaticSite(directory=self.docs_path)
        return {"status": "not_available", "message": f"Docs not built for {self.name}"}

    @route("api")
    def examples(self) -> StaticSite | dict[str, str]:
        """Examples for this module."""
        if self.has_examples:
            return StaticSite(directory=self.examples_path)
        return {"status": "not_available", "message": f"No examples for {self.name}"}

    @route("api")
    def info(self) -> dict[str, Any]:
        """Module information."""
        return {
            "name": self.name,
            "path": str(self.module_path),
            "has_docs": self.has_docs,
            "has_examples": self.has_examples,
        }


# -----------------------------------------------------------------------------
# SysApi: live server management (attached to server, not to Docs)
# -----------------------------------------------------------------------------

class SysApi(RoutingClass):
    """
    API for managing the live ASGI server.

    Endpoints:
    - sites: list active sites
    - add: add a new site
    - remove: remove a site
    - routes: router introspection
    """

    def __init__(self, server: AsgiServer):
        self.server = server
        # Create router with self as owner
        self.router = Router(self, name="api")

    @route("api")
    def sites(self) -> dict[str, Any]:
        """List all active sites."""
        docs = getattr(self.server, "docs", None)
        if docs is None:
            return {}
        return {
            name: {
                "has_docs": site.has_docs,
                "has_examples": site.has_examples,
                "path": str(site.module_path),
            }
            for name, site in docs.sites.items()
        }

    @route("api")
    def add(self, name: str, path: str) -> dict[str, str]:
        """Add a new module site dynamically."""
        docs = getattr(self.server, "docs", None)
        if docs is None:
            return {"status": "error", "message": "Docs not initialized"}

        module_path = Path(path)
        if not module_path.exists():
            return {"status": "error", "message": f"Path not found: {path}"}

        site = ModuleSite(module_path)
        docs.sites[name] = site

        # Store as attribute for attach_instance requirement
        attr_name = f"site_{name.replace('-', '_')}"
        setattr(docs, attr_name, site)

        # Attach to docs router
        docs.router.attach_instance(site, name=name)

        return {"status": "ok", "name": name, "path": path}

    @route("api")
    def remove(self, name: str) -> dict[str, str]:
        """Remove a site."""
        docs = getattr(self.server, "docs", None)
        if docs is None:
            return {"status": "error", "message": "Docs not initialized"}

        if name not in docs.sites:
            return {"status": "error", "message": f"Site not found: {name}"}

        site = docs.sites.pop(name)
        docs.router.detach_instance(site)

        return {"status": "ok", "name": name}

    @route("api")
    def routes(self) -> dict[str, Any]:
        """Router introspection - show all available routes."""
        return self.server.router.members()


# -----------------------------------------------------------------------------
# Docs: documentation hub (contains ModuleSite instances)
# -----------------------------------------------------------------------------

class Docs(RoutingClass):
    """
    Documentation hub for genro modules.

    Scans a directory for genro-* modules and creates ModuleSite
    instances for each. Provides dynamic index page.
    """

    def __init__(self, modules_dir: Path):
        self.modules_dir = Path(modules_dir)
        self.sites: dict[str, ModuleSite] = {}

        # Create router with self as owner
        self.router = Router(self, name="api")

        # Scan for modules
        self._scan_modules()

    def _scan_modules(self) -> None:
        """Scan modules_dir for genro-* directories."""
        if not self.modules_dir.exists():
            return

        for module_path in sorted(self.modules_dir.glob("genro-*")):
            if not module_path.is_dir():
                continue

            name = module_path.name
            site = ModuleSite(module_path)
            self.sites[name] = site

            # Store as attribute for attach_instance requirement
            attr_name = f"site_{name.replace('-', '_')}"
            setattr(self, attr_name, site)

            # Attach to router
            self.router.attach_instance(site, name=name)

    @route("api")
    def index(self) -> HTMLResponse:
        """Generate dynamic index page from router structure."""
        html = self._generate_index_html()
        return HTMLResponse(content=html)

    def _generate_index_html(self) -> str:
        """Generate HTML index from sites."""
        cards = []
        for name, site in sorted(self.sites.items()):
            status = "available" if site.has_docs else "pending"
            status_class = "stable" if site.has_docs else "alpha"
            docs_link = f"/docs/{name}/docs/" if site.has_docs else "#"
            docs_text = "View Documentation &rarr;" if site.has_docs else "Documentation pending"

            cards.append(f'''
            <div class="module-card">
                <h2>
                    <a href="/docs/{name}/">{name}</a>
                    <span class="status {status_class}">{status}</span>
                </h2>
                <p>
                    Docs: {"Yes" if site.has_docs else "No"} |
                    Examples: {"Yes" if site.has_examples else "No"}
                </p>
                <a href="{docs_link}" class="link">{docs_text}</a>
            </div>
            ''')

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Genro Modules - Documentation</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e4e4e4;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px; }}
        header {{ text-align: center; margin-bottom: 60px; }}
        h1 {{ font-size: 3rem; font-weight: 300; margin-bottom: 10px; color: #fff; }}
        h1 span {{ color: #0ea5e9; }}
        .subtitle {{ font-size: 1.2rem; color: #94a3b8; }}
        .modules {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }}
        .module-card {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 24px;
            transition: transform 0.2s, border-color 0.2s;
        }}
        .module-card:hover {{ transform: translateY(-4px); border-color: #0ea5e9; }}
        .module-card h2 {{ font-size: 1.4rem; margin-bottom: 12px; color: #fff; }}
        .module-card h2 a {{ color: inherit; text-decoration: none; }}
        .module-card h2 a:hover {{ color: #0ea5e9; }}
        .module-card p {{ color: #94a3b8; line-height: 1.6; margin-bottom: 16px; }}
        .module-card .link {{ display: inline-block; color: #0ea5e9; text-decoration: none; font-weight: 500; }}
        .module-card .link:hover {{ text-decoration: underline; }}
        .status {{
            display: inline-block; padding: 4px 10px; border-radius: 20px;
            font-size: 0.75rem; font-weight: 600; text-transform: uppercase; margin-left: 8px;
        }}
        .status.alpha {{ background: rgba(234, 179, 8, 0.2); color: #eab308; }}
        .status.stable {{ background: rgba(34, 197, 94, 0.2); color: #22c55e; }}
        footer {{
            text-align: center; margin-top: 60px; padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1); color: #64748b;
        }}
        footer a {{ color: #0ea5e9; text-decoration: none; }}
        .api-info {{
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 16px;
            margin-top: 40px;
            font-family: monospace;
        }}
        .api-info h3 {{ color: #0ea5e9; margin-bottom: 12px; }}
        .api-info code {{ color: #94a3b8; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Genro <span>Modules</span></h1>
            <p class="subtitle">Documentation Hub</p>
            <p class="subtitle" style="margin-top: 8px; font-size: 0.9rem;">
                {len(self.sites)} modules discovered
            </p>
        </header>

        <div class="modules">
            {"".join(cards)}
        </div>

        <div class="api-info">
            <h3>API Endpoints</h3>
            <p><code>/_sys/sites</code> - List all sites</p>
            <p><code>/_sys/routes</code> - Router introspection</p>
            <p><code>/_sys/add?name=X&path=Y</code> - Add site dynamically</p>
            <p><code>/_sys/remove?name=X</code> - Remove site</p>
        </div>

        <footer>
            <p>
                Powered by <a href="https://github.com/genropy/genro-asgi">genro-asgi</a> +
                <a href="https://github.com/genropy/genro-routes">genro-routes</a> |
                &copy; 2025 Softwell S.r.l.
            </p>
        </footer>
    </div>
</body>
</html>'''


if __name__ == "__main__":
    # Quick test
    modules_dir = Path(__file__).parent.parent.parent.parent  # sub-projects/
    print(f"Scanning: {modules_dir}")

    docs = Docs(modules_dir)
    print(f"Found {len(docs.sites)} modules:")
    for name, site in docs.sites.items():
        print(f"  {name}: docs={site.has_docs}, examples={site.has_examples}")

    print("\nRouter members:")
    print(docs.router.members())
