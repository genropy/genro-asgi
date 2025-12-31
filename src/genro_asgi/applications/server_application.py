# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ServerApplication - System endpoints for AsgiServer.

Endpoint di sistema:
- index: pagina default con redirect a main_app
- openapi: schema OpenAPI del server
- resource: loader risorse con fallback gerarchico
- create_jwt: creazione JWT (richiede superadmin)

Montato automaticamente come /_server/ dal server.
Modulo interno - non esportato in __init__.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from genro_routes import RoutingClass, Router, route  # type: ignore[import-untyped]

from ..exceptions import HTTPNotFound, Redirect

if TYPE_CHECKING:
    from ..server import AsgiServer

__all__ = ["ServerApplication"]


class ServerApplication(RoutingClass):
    """System endpoints for AsgiServer. Mounted at /_server/."""

    __slots__ = ("_server", "main")

    def __init__(self, server: AsgiServer) -> None:
        """Initialize ServerApplication with reference to parent server."""
        self._server = server
        self.main = Router(self, name="main")

    @property
    def config(self) -> Any:
        """Server configuration."""
        return self._server.config

    @property
    def main_app(self) -> str | None:
        """Return main app name: configured or single app."""
        configured: str | None = self.config["main_app"]
        if configured:
            return configured
        apps: dict[str, Any] = self.config["apps"] or {}
        return next(iter(apps)) if len(apps) == 1 else None

    @route(meta_mime_type="text/html")
    def index(self) -> str:
        """Default index page. Redirects to main_app if configured."""
        if self.main_app:
            raise Redirect(f"/{self.main_app}/")
        # resources/ è in genro_asgi/, risaliamo di un livello da applications/
        html_path = Path(__file__).parent.parent / "resources" / "html" / "default_index.html"
        return html_path.read_text()

    @route(meta_mime_type="application/json")
    def openapi(self, *args: str) -> dict[str, Any]:
        """OpenAPI schema endpoint."""
        basepath = "/".join(args) if args else None
        paths = self._server.router.nodes(basepath=basepath, mode="openapi")
        return {
            "openapi": "3.1.0",
            "info": self._server.openapi_info,
            **paths,
        }

    @route(name="resource")
    def load_resource(self, *args: str, name: str) -> Any:
        """Load resource with hierarchical fallback."""
        result = self._server.resource_loader.load(*args, name=name)
        if result is None:
            raise HTTPNotFound(f"Resource not found: {name}")
        content, mime_type = result
        return self.result_wrapper(content, mime_type=mime_type)

    @route(auth_tags="superadmin&has_jwt")
    def create_jwt(
        self,
        jwt_config: str | None = None,
        sub: str | None = None,
        tags: str | None = None,
        exp: int | None = None,
        **extra_kwargs: Any,
    ) -> dict[str, Any]:
        """Create JWT token via HTTP endpoint. Requires superadmin auth tag."""
        if not jwt_config or not sub:
            return {"error": "jwt_config and sub are required"}
        _ = (tags, exp, extra_kwargs)  # unused until genro-toolbox is ready
        return {"error": "not implemented - waiting for genro-toolbox"}
