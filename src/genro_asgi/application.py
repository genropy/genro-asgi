# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""AsgiApplication - Base class for ASGI applications."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from genro_routes import Router, RoutingClass, route  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from .server import AsgiServer

__all__ = ["AsgiApplication"]


class AsgiApplication(RoutingClass):
    """Base class for apps mounted on AsgiServer.

    Provides default `main` router and `index()` method. Subclasses define
    `openapi_info` for metadata and add routes with @route() decorator.

    Example::

        class MyApp(AsgiApplication):
            openapi_info = {"title": "My API", "version": "1.0.0"}

            @route()  # Uses the only router (self.main) automatically
            def hello(self):
                return "Hello!"

            def __init__(self, **kwargs):
                super().__init__(**kwargs)  # Required: creates self.main
                self.backoffice = Router(self, name="backoffice")

            @route("backoffice")  # Must specify when multiple routers
            def admin(self):
                return "Admin panel"
    """

    openapi_info: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        """Initialize app with default main router."""
        self.base_dir = kwargs.pop("base_dir", None)
        self.main = Router(self, name="main")
        self.on_init(**kwargs)

    def on_init(self, **kwargs: Any) -> None:
        """Called after base initialization. Override for custom setup.

        Args:
            **kwargs: Parameters from config.yaml app definition.
        """
        pass

    @property
    def server(self) -> AsgiServer | None:
        """Return the server that mounted this app (semantic alias for _routing_parent)."""
        return getattr(self, "_routing_parent", None)

    def on_startup(self) -> None:
        """Called when server starts. Override for custom initialization.

        Can be sync or async. Called after all apps are mounted.
        """
        pass

    def on_shutdown(self) -> None:
        """Called when server stops. Override for custom cleanup.

        Can be sync or async. Called in reverse order of startup.
        """
        pass

    def load_resource(self, *args: str, name: str) -> Any:
        """Load resource via server's ResourceLoader, prepending this app's mount name."""
        if not self.server:
            return None
        mount_name = getattr(self, "_mount_name", "")
        return self.server.load_resource(mount_name, *args, name=name)

    @route(meta_mime_type="text/html")
    def index(self) -> str:
        """Return HTML splash page. Override for custom index."""
        info = getattr(self, "openapi_info", {})
        title = info.get("title", self.__class__.__name__)
        version = info.get("version", "")
        description = info.get("description", "")

        version_html = f"<p>Version: {version}</p>" if version else ""
        desc_html = f"<p>{description}</p>" if description else ""

        return f"""<!DOCTYPE html>
<html>
<head><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
h1 {{ color: #333; }}
</style>
</head>
<body>
<h1>{title}</h1>
{version_html}
{desc_html}
</body>
</html>"""


if __name__ == "__main__":
    app = AsgiApplication()
    print(f"Router: {app.main}")
    print(f"Routes: {app.routing}")
