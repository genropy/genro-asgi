# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""System endpoints for AsgiServer.

This module provides built-in endpoints for server-level operations,
automatically mounted at /_server/ path.

Endpoints:
    /: Index page with redirect to main application if configured.
    /openapi: OpenAPI 3.1 schema generation for all mounted apps.
    /resource/<path>: Hierarchical resource loader with fallback chain.
    /create_jwt: JWT token creation (requires superadmin auth tag).

The ServerApplication implements RoutingClass interface from genro-routes
and integrates with the server's router for endpoint routing.

Note:
    Internal module - not exported in package __init__.py.
    Mounted automatically by AsgiServer at /_server/ path.

Example:
    Server automatically creates and mounts this application::

        server = AsgiServer()
        # ServerApplication available at /_server/
        # GET /_server/ -> redirects to main app or shows default page
        # GET /_server/openapi -> returns OpenAPI schema
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from genro_routes import RoutingClass, Router, route  # type: ignore[import-untyped]

from ...exceptions import HTTPNotFound, Redirect

if TYPE_CHECKING:
    from ..server import AsgiServer

__all__ = ["ServerApplication"]


class ServerApplication(RoutingClass):
    """System endpoints for AsgiServer.

    Provides built-in HTTP endpoints for server-level operations.
    Implements RoutingClass interface for integration with genro-routes.

    Attributes:
        main: Router instance for endpoint registration.

    Note:
        Automatically mounted at /_server/ by AsgiServer.
        Access parent server via _server attribute (dual relationship pattern).
    """

    __slots__ = ("_server", "main")

    def __init__(self, server: AsgiServer) -> None:
        """Initialize ServerApplication.

        Args:
            server: Parent AsgiServer instance (dual relationship).
        """
        self._server = server
        self.main = Router(self, name="main")

    @property
    def config(self) -> Any:
        """Any: Server configuration object from parent AsgiServer."""
        return self._server.config

    @property
    def main_app(self) -> str | None:
        """str | None: Main application name for redirect.

        Returns the configured main_app from server config, or if only
        one app is mounted, returns that app's name. Returns None if
        multiple apps exist and no main_app is configured.
        """
        configured: str | None = self.config["main_app"]
        if configured:
            return configured
        apps: dict[str, Any] = self.config["apps"] or {}
        return next(iter(apps)) if len(apps) == 1 else None

    @route(meta_mime_type="text/html")
    def index(self) -> str:
        """Server index page endpoint.

        If a main_app is configured (or only one app exists), redirects
        to that application. Otherwise, serves a default HTML welcome page.

        Returns:
            HTML content of default index page (only if no redirect).

        Raises:
            Redirect: 307 redirect to main_app if one is configured.

        Note:
            Route: GET /_server/
            Content-Type: text/html
        """
        if self.main_app:
            raise Redirect(f"/{self.main_app}/")
        # resources are in the same directory as this module
        html_path = Path(__file__).parent / "resources" / "index.html"
        return html_path.read_text()

    @route(meta_mime_type="application/json")
    def openapi(self, *args: str) -> dict[str, Any]:
        """Generate OpenAPI 3.1 schema for server endpoints.

        Produces OpenAPI specification documenting all mounted applications
        and their routes. Can filter to a specific basepath.

        Args:
            *args: Optional path segments to filter schema (e.g., "myapp", "api").
                   Joined with "/" to form basepath filter.

        Returns:
            OpenAPI 3.1 schema dict with keys: openapi, info, paths, components.

        Note:
            Route: GET /_server/openapi or /_server/openapi/<basepath>
            Content-Type: application/json
        """
        basepath = "/".join(args) if args else None
        paths = self._server.router.nodes(basepath=basepath, mode="openapi")
        return {
            "openapi": "3.1.0",
            "info": self._server.openapi_info,
            **paths,
        }

    @route(name="resource")
    def load_resource(self, *args: str, name: str) -> Any:
        """Load resource with hierarchical fallback chain.

        Searches for resource using the server's ResourceLoader, which
        implements a fallback chain through app-specific and server-wide
        resource directories.

        Args:
            *args: Path segments for resource location (e.g., "css", "themes").
            name: Resource filename to load (required query parameter).

        Returns:
            Resource content wrapped with appropriate MIME type.

        Raises:
            HTTPNotFound: If resource is not found in any fallback location.

        Note:
            Route: GET /_server/resource/<path>?name=<filename>
            Fallback chain: app resources -> server resources -> package resources
        """
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
        """Create JWT token via HTTP endpoint.

        Generates a new JWT token with specified claims. Requires caller
        to have both 'superadmin' and 'has_jwt' auth tags.

        Args:
            jwt_config: JWT configuration name from server config.
            sub: Subject claim - typically user identifier.
            tags: Optional auth tags to embed in token.
            exp: Optional expiration time in seconds from now.
            **extra_kwargs: Additional claims to include in token payload.

        Returns:
            Dict with 'token' key on success, or 'error' key on failure.

        Note:
            Route: POST /_server/create_jwt
            Auth: Requires superadmin & has_jwt tags
            Status: Not yet implemented - waiting for genro-toolbox integration.
        """
        if not jwt_config or not sub:
            return {"error": "jwt_config and sub are required"}
        _ = (tags, exp, extra_kwargs)  # unused until genro-toolbox is ready
        return {"error": "not implemented - waiting for genro-toolbox"}
