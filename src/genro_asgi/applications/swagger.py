# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""SwaggerApp - OpenAPI/Swagger documentation app."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from genro_routes import Router, route  # type: ignore[import-untyped]

from .base import AsgiApplication

if TYPE_CHECKING:
    from ..response import Response

__all__ = ["SwaggerApp"]


class SwaggerApp(AsgiApplication):
    """Swagger UI and OpenAPI schema app.

    Mount in config.yaml:
        apps:
          _swagger:
            module: "genro_asgi.applications:SwaggerApp"
    """

    def __init__(self, **kwargs: Any) -> None:
        self.server = kwargs.pop("_server", None)
        self.api = Router(self, name="api")

    @route("api")
    def index(self, app: str = "") -> Response:
        """Swagger UI page."""
        from ..response import HTMLResponse

        html_path = Path(__file__).parents[1] / "resources" / "swagger.html"
        html = html_path.read_text()
        # Adjust openapi URL to be relative to swagger mount point
        base_path = "/_swagger"
        html = html.replace(
            "/_openapi_json", f"{base_path}/openapi?app={app}" if app else f"{base_path}/openapi"
        )
        return HTMLResponse(content=html)

    @route("api")
    def openapi(self, app: str = "") -> dict:
        """OpenAPI schema."""
        if not self.server:
            return {"openapi": "3.0.3", "info": {"title": "API", "version": "1.0.0"}, "paths": {}}

        if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                paths = instance.api.nodes(mode="openapi").get("paths", {})
                title = getattr(instance, "title", app)
                version = getattr(instance, "version", "1.0.0")
            else:
                paths = {}
                title = app
                version = "1.0.0"
        else:
            paths = self.server.router.nodes(mode="openapi").get("paths", {})
            title = "GenroASGI API"
            version = "1.0.0"

        return {
            "openapi": "3.0.3",
            "info": {"title": title, "version": version},
            "paths": paths,
        }


if __name__ == "__main__":
    pass
