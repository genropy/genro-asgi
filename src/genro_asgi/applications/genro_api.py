# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""GenroApiApp - Custom API Explorer application."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from genro_routes import Router, route  # type: ignore[import-untyped]

from .base import AsgiApplication

if TYPE_CHECKING:
    from ..response import Response

__all__ = ["GenroApiApp"]


class GenroApiApp(AsgiApplication):
    """Genro API Explorer - custom API documentation UI.

    Mount in config.yaml:
        apps:
          _genro_api:
            module: "genro_asgi.applications:GenroApiApp"
    """

    def __init__(self, **kwargs: Any) -> None:
        self.server = kwargs.pop("_server", None)
        self.api = Router(self, name="api")

    @route("api")
    def index(self) -> Response:
        """Serve the main explorer page."""
        from ..response import HTMLResponse

        html_path = Path(__file__).parents[1] / "resources" / "genro_api" / "index.html"
        html = html_path.read_text()
        return HTMLResponse(content=html)

    @route("api")
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

    @route("api")
    def static(self, file: str = "") -> Response:
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
