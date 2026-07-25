# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Error middleware: the outermost try/except of the chain and the login seam.

``ErrorMiddleware`` (order 100, the only middleware enabled by default —
``errors=False`` disables it) maps control-flow exceptions to responses:
``Redirect`` → its status plus the ``Location`` header, ``HTTPException`` →
its status with the detail, any other ``Exception`` → a hidden 500 logged via
the instance logger. Responses are built with the ``Response`` class; an
exception's ``headers`` (e.g. a ``WWW-Authenticate`` challenge) are forwarded
onto the response.

Content negotiation (D4 error-body reconciliation): the error body follows the
caller's ``Accept``. A caller asking for JSON (``application/json`` or ``*/*``,
never ``text/html``) gets the ``{"error": ...}`` document built by
``Response.set_error`` — the single live JSON error path; anyone else keeps the
historical ``text/plain`` body. A missing ``Accept`` stays ``text/plain`` (the
pre-existing default).

Challenge negotiation (only when the server carries an active login surface —
``server.login_enabled``): a 401 is where the server asks the caller to
authenticate. A browser NAVIGATION (an http GET whose ``Accept`` includes
``text/html``) gets a 302 to ``/_server/login_page`` carrying the original
path+query as a ``safe_next_path``-validated ``next``; any other caller keeps
the bare 401 (with its ``WWW-Authenticate``) and gains a ``{"login_url": ...}``
JSON body so an SPA can drive the login. With the login surface off the 401 is
answered exactly like any other error. The request shape is read from the scope
headers (``headers_dict``) — never an ambient request.

The middleware wraps ``send`` to track whether ``http.response.start`` has
already passed downstream: an exception raised AFTER the response started
cannot be answered (a second start would corrupt the stream), so it is logged
and re-raised — the server/transport tears the connection down. The chain only
carries ``http`` scopes (the mixin routes the others past it), so no scope
filtering happens here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

from ..auth import safe_next_path
from ..exceptions import HTTPException, Redirect
from ..response import Response
from .base import BaseMiddleware, headers_dict

if TYPE_CHECKING:
    from ..types import Message, Receive, Scope, Send

__all__ = ["ErrorMiddleware"]

LOGIN_PAGE_URL = "/_server/login_page"


class ErrorMiddleware(BaseMiddleware):
    """Outermost middleware answering raised exceptions with HTTP responses."""

    middleware_order = 100
    middleware_default = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the chain; map raised exceptions to responses unless already started."""
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:
                self.logger.exception(
                    "error after response started serving %s", scope.get("path", "?")
                )
                raise
            response = self._response_for(exc, scope)
            await response(scope, receive, send)

    def _response_for(self, exc: Exception, scope: Scope) -> Response:
        """The challenge response for an active-login 401, otherwise the error response."""
        if isinstance(exc, HTTPException) and exc.status == 401 and self._login_active():
            return self._challenge_response(exc, scope)
        return self._error_response(exc, scope)

    def _login_active(self) -> bool:
        """True when the server carries an active login surface (``login_enabled``).

        Used standalone (no server, or one without a login surface) the
        middleware answers the 401 unchanged.
        """
        return bool(getattr(self.server, "login_enabled", False))

    def _challenge_response(self, exc: HTTPException, scope: Scope) -> Response:
        """Negotiate a 401 into a browser redirect or an API-friendly 401.

        A browser navigation gets a 302 to the login page with the original
        path+query as a validated ``next``; any other caller keeps the bare 401
        (with its ``WWW-Authenticate``) and gains a ``{"login_url": ...}`` body.
        """
        headers = headers_dict(scope)
        if self._is_browser_navigation(scope, headers):
            target = safe_next_path(self._original_target(scope))
            response = Response(status_code=302, media_type="text/plain")
            response.set_header("location", f"{LOGIN_PAGE_URL}?next={quote(target, safe='')}")
            return response
        response = Response(status_code=401)
        response.set_result({"login_url": LOGIN_PAGE_URL})
        self._forward_headers(response, exc)
        return response

    def _is_browser_navigation(self, scope: Scope, headers: dict[str, str]) -> bool:
        """True for an http GET whose ``Accept`` asks for HTML (a navigation)."""
        if str(scope.get("method", "")).upper() != "GET":
            return False
        return "text/html" in headers.get("accept", "")

    def _original_target(self, scope: Scope) -> str:
        """Rebuild the request's original path (+query) for the ``next`` value."""
        path = str(scope.get("path", "/"))
        query = scope.get("query_string", b"")
        query_str = query.decode("latin-1") if isinstance(query, bytes) else str(query)
        return f"{path}?{query_str}" if query_str else path

    def _error_response(self, exc: Exception, scope: Scope) -> Response:
        """Build the ``Response`` for a raised exception, negotiating the body format."""
        if isinstance(exc, Redirect):
            response = Response(status_code=exc.status, media_type="text/plain")
            response.set_header("location", exc.location)
            self._forward_headers(response, exc)
            return response
        wants_json = self._wants_json(headers_dict(scope))
        if isinstance(exc, HTTPException):
            if wants_json:
                response = Response()
                response.set_error(exc)
            else:
                response = Response(
                    content=exc.detail or "", status_code=exc.status, media_type="text/plain"
                )
        else:
            self.logger.exception("unhandled error serving %s", scope.get("path", "?"))
            if wants_json:
                response = Response(status_code=500)
                response.set_result({"error": "Internal Server Error"})
            else:
                response = Response(
                    content="Internal Server Error", status_code=500, media_type="text/plain"
                )
        self._forward_headers(response, exc)
        return response

    def _wants_json(self, headers: dict[str, str]) -> bool:
        """True when the caller's ``Accept`` asks for JSON (never for a browser navigation).

        A missing ``Accept`` keeps the historical ``text/plain`` default; an
        ``Accept`` naming ``text/html`` (a browser) also stays text; only an API
        caller (``application/json`` or ``*/*``) gets the JSON error document.
        """
        accept = headers.get("accept", "")
        if not accept or "text/html" in accept:
            return False
        return "application/json" in accept or "*/*" in accept

    def _forward_headers(self, response: Response, exc: Exception) -> None:
        """Forward an exception's ASGI header pairs onto the response."""
        for name, value in getattr(exc, "headers", []):
            response.set_header(name.decode("latin-1"), value.decode("latin-1"))
