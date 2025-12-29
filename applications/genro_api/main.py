# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""GenroApiApp - Custom API Explorer application."""

from __future__ import annotations

from pathlib import Path

from genro_routes import route  # type: ignore[import-untyped]

from genro_asgi import AsgiApplication

__all__ = ["GenroApiApp"]


class GenroApiApp(AsgiApplication):
    """Genro API Explorer - custom API documentation UI.

    Mount in config.yaml:
        apps:
          _genro_api:
            module: "main:GenroApiApp"
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
        html_path = self.base_dir / "resources" / "index.html"
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
    def apps(self) -> dict:
        """Return list of available apps with API routers."""
        if not self.server:
            return {"apps": []}

        app_list = []
        for name, instance in self.server.apps.items():
            if hasattr(instance, "api"):
                app_list.append({"name": name, "has_api": True})
        return {"apps": app_list}

    @route()
    def nodes(self, app: str = "", basepath: str = "", lazy: bool = False) -> dict:
        """Return hierarchical OpenAPI schema for tree view.

        Args:
            app: App name to get schema for (empty = server router)
            basepath: Base path for lazy loading subtrees
            lazy: If True, don't expand child routers
        """
        if not self.server:
            return {"description": None, "owner_doc": None, "paths": {}, "routers": {}}

        # Get auth_tags and capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.capabilities if request else ""

        if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                result: dict = instance.api.nodes(
                    mode="h_openapi",
                    basepath=basepath,
                    lazy=lazy,
                    auth_tags=auth_tags,
                    env_capabilities=capabilities,
                )
                return result
            return {"description": None, "owner_doc": None, "paths": {}, "routers": {}}

        result = self.server.router.nodes(
            mode="h_openapi",
            basepath=basepath,
            lazy=lazy,
            auth_tags=auth_tags,
            env_capabilities=capabilities,
        )
        return dict(result)

    @route(openapi_method="get")
    def getdoc(self, path: str, app: str = "") -> dict:
        """Get documentation for a single node (router or endpoint).

        Args:
            path: The path to the node (e.g., "/table/article/get")
            app: App name (empty = server router)
        """
        if not self.server:
            return {"error": "No server available"}

        router = None
        if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                router = instance.api
        else:
            router = self.server.router

        if not router:
            return {"error": f"Router not found for app '{app}'"}

        # Get auth_tags and capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.capabilities if request else ""

        # Remove leading slash - router.node() expects path without it
        clean_path = path.lstrip("/")
        node = router.node(
            clean_path,
            mode="openapi",
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

        resources_dir = self.base_dir / "resources"
        file_path = resources_dir / file

        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Resource not found: {file}")

        return file_path


if __name__ == "__main__":
    pass
