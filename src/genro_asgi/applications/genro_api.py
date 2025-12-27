# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""GenroApiApp - Custom API Explorer application."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genro_routes import route  # type: ignore[import-untyped]

from ..application import AsgiApplication

__all__ = ["GenroApiApp"]


class GenroApiApp(AsgiApplication):
    """Genro API Explorer - custom API documentation UI.

    Mount in config.yaml:
        apps:
          _genro_api:
            module: "genro_asgi.applications:GenroApiApp"
    """

    @route(mime_type="text/html")
    def index(self, *args: str) -> str:
        """Serve the main explorer page.

        With path consumption: /_genro_api/shop calls index('shop')
        """
        app_name = args[0] if args else ""
        return self._serve_explorer(app=app_name)

    def _serve_explorer(self, app: str = "") -> str:
        """Serve the explorer HTML, optionally with app preselected."""
        html_path = Path(__file__).parents[1] / "resources" / "genro_api" / "index.html"
        html = html_path.read_text()

        if app:
            # Inject script to preselect app on load
            init_script = f"""
    <script type="module">
      window.GENRO_API_INITIAL_APP = "{app}";
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

        if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                result: dict = instance.api.nodes(mode="h_openapi", basepath=basepath, lazy=lazy)
                return result
            return {"description": None, "owner_doc": None, "paths": {}, "routers": {}}

        result = self.server.router.nodes(mode="h_openapi", basepath=basepath, lazy=lazy)
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

        # Remove leading slash - router.get() expects path without it
        clean_path = path.lstrip("/")
        result: dict = router.node(clean_path, mode="openapi")
        return result

    @route()
    def static(self, file: str = "") -> Any:
        """Serve static resources (JS, CSS) from resources folder."""
        from ..response import Response

        if not file:
            return Response(content=b"File parameter required", status_code=400)

        resources_dir = Path(__file__).parents[1] / "resources" / "genro_api"
        file_path = resources_dir / file

        if not file_path.exists() or not file_path.is_file():
            return Response(content=b"Not found", status_code=404)

        content = file_path.read_bytes()

        media_types = {
            ".js": "application/javascript",
            ".css": "text/css",
            ".html": "text/html",
            ".json": "application/json",
        }
        media_type = media_types.get(file_path.suffix, "application/octet-stream")

        return Response(content=content, media_type=media_type)


if __name__ == "__main__":
    pass
