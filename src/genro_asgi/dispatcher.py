# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Dispatcher - Routes requests to handlers via genro_routes Router."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from genro_routes import RouterInterface

from .request import (
    ResponseBuilder,
    set_current_request,
    set_current_response,
)
from .response import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response

if TYPE_CHECKING:
    from .server import AsgiServer
    from .types import Receive, Scope, Send


class Dispatcher:
    """Routes ASGI requests to handlers via genro_routes Router."""

    __slots__ = ("server",)

    def __init__(self, server: AsgiServer) -> None:
        self.server = server

    @property
    def router(self) -> Any:
        """Proxy to server.router."""
        return self.server.router

    @property
    def request_registry(self) -> Any:
        """Proxy to server.request_registry."""
        return self.server.request_registry

    @property
    def logger(self) -> Any:
        """Proxy to server.logger."""
        return self.server.logger

    def _make_response(self, result: Any, response_builder: ResponseBuilder) -> Response:
        """Convert handler result to Response, respecting ResponseBuilder settings."""
        # If handler explicitly set content_type, honor it
        if response_builder.content_type:
            content_type = response_builder.content_type
            if content_type == "text/html":
                return HTMLResponse(str(result))
            if content_type == "text/plain":
                return PlainTextResponse(str(result))
            if content_type == "application/json":
                return JSONResponse(result)
            # For other content types, use PlainTextResponse with custom media_type
            return PlainTextResponse(str(result), media_type=content_type)

        # Default: auto-detect from result type
        if isinstance(result, Response):
            return result
        if isinstance(result, dict):
            return JSONResponse(result)
        if isinstance(result, list):
            return JSONResponse(result)
        if isinstance(result, str):
            # Auto-detect HTML by checking structure
            stripped = result.strip()
            if stripped.startswith("<") and stripped.endswith(">"):
                return HTMLResponse(result)
            return PlainTextResponse(result)
        if result is None:
            return PlainTextResponse("")
        return PlainTextResponse(str(result))

    def _render_nodes_html(self, path: str, router: RouterInterface) -> HTMLResponse:
        """Render router nodes as HTML directory listing."""
        path = path.rstrip("/")
        nodes_data = router.nodes()

        items_html = []
        # entries are handlers (📄)
        for name in nodes_data.get("entries", {}):
            href = f"{path}/{name}"
            items_html.append(f'<li><a href="{href}">📄 {name}</a></li>')
        # routers are children (📁)
        for name in nodes_data.get("routers", {}):
            href = f"{path}/{name}"
            items_html.append(f'<li><a href="{href}">📁 {name}</a></li>')

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Index of {path}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #1a1a2e; color: #e4e4e4; }}
h1 {{ color: #0ea5e9; }}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 0.5rem 0; }}
a {{ color: #22c55e; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style></head>
<body><h1>Index of {path}/</h1>
<ul>{''.join(items_html)}</ul>
</body></html>"""
        return HTMLResponse(html)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - dispatch request to handler via router."""
        path = scope.get("path", "/")
        selector = path.strip("/")

        handler = self.router.get(selector, partial=True)

        # If we got a router (not a handler), show members
        if isinstance(handler, RouterInterface):
            response = self._render_nodes_html(path, handler)
            await response(scope, receive, send)
            return

        if handler is None:
            err_response: Response = JSONResponse(
                {"error": f"Not found: {path}"},
                status_code=404,
            )
            await err_response(scope, receive, send)
            return

        request = await self.request_registry.create(scope, receive, send)

        # Set app_name from first path segment for metrics
        parts = path.strip("/").split("/")
        if parts and parts[0]:
            request.app_name = parts[0]

        # Create response builder BEFORE calling handler
        response_builder = ResponseBuilder()

        # Set ContextVars so handler code can access request/response via app properties
        set_current_request(request)
        set_current_response(response_builder)

        try:
            kwargs = dict(request.query)

            sig = inspect.signature(handler)
            params = list(sig.parameters.keys())

            if params and params[0] in ("request", "req"):
                result = handler(request, **kwargs)
            else:
                result = handler(**kwargs)

            if inspect.isawaitable(result):
                result = await result

            # Handle file responses from StaticRouter
            if isinstance(result, dict) and result.get("type") == "file":
                # Store file path in scope for cache middleware
                scope["_file_path"] = result["path"]
                handler_response = FileResponse(result["path"])
            else:
                handler_response = self._make_response(result, response_builder)

            await handler_response(scope, receive, send)

        except Exception as e:
            self.logger.exception(f"Handler error: {e}")
            exc_response: Response = JSONResponse(
                {"error": str(e)},
                status_code=500,
            )
            await exc_response(scope, receive, send)
        finally:
            # Clear ContextVars
            set_current_request(None)
            set_current_response(None)
            self.request_registry.unregister(request.id)


if __name__ == "__main__":
    pass
