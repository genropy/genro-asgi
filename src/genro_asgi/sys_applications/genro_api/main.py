# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""GenroApiApp - Custom API Explorer application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genro_routes import route  # type: ignore[import-untyped]
from genro_routes.core import BaseRouter  # type: ignore[import-untyped]

from genro_asgi import AsgiApplication

__all__ = ["GenroApiApp"]


class GenroApiApp(AsgiApplication):
    """Genro API Explorer - custom API documentation UI.

    Mount in config.yaml as sys_app:
        sys_apps:
          genro_api:
            module: "genro_asgi.sys_applications.genro_api:GenroApiApp"
    """

    openapi_info = {
        "title": "Genro API Explorer",
        "version": "1.0.0",
        "description": "Interactive API documentation and testing interface",
    }

    @route(meta_mime_type="text/html")
    def index(self, *args: str) -> str:
        """Serve the main explorer page.

        With path consumption at N levels:
        - /_genro_api/shop → app="shop", basepath=""
        - /_genro_api/shop/article → app="shop", basepath="article"
        - /_genro_api/shop/article/sub → app="shop", basepath="article/sub"
        """
        app_name = args[0] if args else ""
        basepath = "/".join(args[1:]) if len(args) > 1 else ""
        return self._serve_explorer(app=app_name, basepath=basepath)

    def _serve_explorer(self, app: str = "", basepath: str = "") -> str:
        """Serve the explorer HTML with optional app and basepath preselected."""
        if self.base_dir is None:
            return "<html><body>No base_dir configured</body></html>"
        html_path = Path(self.base_dir) / "resources" / "index.html"
        html = html_path.read_text()

        if app or basepath:
            # Inject script to preselect app and basepath on load
            init_script = f"""
    <script type="module">
      window.GENRO_API_INITIAL_APP = "{app}";
      window.GENRO_API_INITIAL_BASEPATH = "{basepath}";
    </script>
  </head>"""
            html = html.replace("</head>", init_script)

        return html

    @route(openapi_method="get")
    def apps(self) -> dict[str, Any]:
        """Return list of available apps."""
        if not self.server:
            return {"apps": []}

        app_list = [{"name": name} for name in self.server.apps]
        return {"apps": app_list}

    @route()
    def nodes(self, app: str = "", basepath: str = "", lazy: bool = False) -> dict[str, Any]:
        """Return hierarchical OpenAPI schema for tree view.

        Args:
            app: App name to get schema for (empty = server router)
            basepath: Base path for lazy loading subtrees
            lazy: If True, don't expand child routers
        """
        if not self.server:
            return {"description": None, "owner_doc": None, "paths": {}, "routers": {}}

        # Get auth_tags and env_capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.env_capabilities if request else ""

        # Get router: app-specific or server root
        router: BaseRouter = self.server.router
        if app:
            app_router = self.server.router.router_at_path(app)
            if not app_router:
                return {"description": None, "owner_doc": None, "paths": {}, "routers": {}}
            router = app_router

        result = router.nodes(
            mode="h_openapi",
            basepath=basepath,
            lazy=lazy,
            auth_tags=auth_tags,
            env_capabilities=capabilities,
        )
        return dict(result)

    @route(openapi_method="get")
    def getdoc(self, path: str, app: str = "") -> dict[str, Any]:
        """Get documentation for a single node (router or endpoint).

        Args:
            path: The path to the node (e.g., "/table/article/get")
            app: App name (empty = server router)
        """
        if not self.server:
            return {"error": "No server available"}

        # Get router: app-specific or server root
        router: BaseRouter = self.server.router
        if app:
            app_router = self.server.router.router_at_path(app)
            if not app_router:
                return {"error": f"Router not found for app '{app}'"}
            router = app_router

        # Get auth_tags and env_capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.env_capabilities if request else ""

        # Remove leading slash - router.node() expects path without it
        clean_path = path.lstrip("/")
        node = router.node(
            clean_path,
            openapi=True,
            auth_tags=auth_tags,
            env_capabilities=capabilities,
        )
        # RouterNode.openapi contains the OpenAPI schema dict
        return node.openapi or {"error": f"No OpenAPI schema for '{path}'"}

    @route()
    def static(self, file: str = "") -> Path:
        """Serve static resources (JS, CSS) from resources folder.

        Returns Path - set_result() handles mime type detection.
        Raises ValueError/FileNotFoundError for errors (mapped by set_error()).
        """
        if not file:
            raise ValueError("File parameter required")

        if self.base_dir is None:
            raise ValueError("No base_dir configured")

        resources_dir = Path(self.base_dir) / "resources"
        file_path = resources_dir / file

        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Resource not found: {file}")

        return file_path


if __name__ == "__main__":
    pass
