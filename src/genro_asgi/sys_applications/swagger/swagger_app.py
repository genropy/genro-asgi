# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Swagger - OpenAPI/Swagger documentation app."""

from __future__ import annotations

from typing import Any

from genro_routes import route  # type: ignore[import-untyped]

from genro_asgi import AsgiApplication

__all__ = ["Application"]


class Application(AsgiApplication):
    """Swagger UI and OpenAPI schema app.

    Mount in config.yaml as sys_app:
        sys_apps:
          swagger:
            module: "genro_asgi.sys_applications.swagger.swagger_app:Application"
    """

    openapi_info = {
        "title": "Swagger UI",
        "version": "1.0.0",
        "description": "OpenAPI/Swagger documentation interface",
    }

    @route()
    def index(self) -> Any:
        """Swagger UI page with toolbar."""
        result = self.load_resource(name="index.html")
        if result is None:
            return "Resource not found: index.html"
        content, mime_type = result
        return self.result_wrapper(content, mime_type=mime_type)

    @route()
    def openapi(self, app: str = "") -> dict[str, Any]:
        """OpenAPI schema."""
        if not self.server:
            return {"openapi": "3.0.3", "info": {"title": "API", "version": "1.0.0"}, "paths": {}}

        # Get auth_tags and env_capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.env_capabilities if request else ""

        if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                paths = instance.api.nodes(
                    mode="openapi",
                    auth_tags=auth_tags,
                    env_capabilities=capabilities,
                ).get("paths", {})
                title = getattr(instance, "title", app)
                version = getattr(instance, "version", "1.0.0")
            else:
                paths = {}
                title = app
                version = "1.0.0"
        else:
            paths = self.server.router.nodes(
                mode="openapi",
                auth_tags=auth_tags,
                env_capabilities=capabilities,
            ).get("paths", {})
            title = "GenroASGI API"
            version = "1.0.0"

        return {
            "openapi": "3.0.3",
            "info": {"title": title, "version": version},
            "paths": paths,
        }


if __name__ == "__main__":
    pass
