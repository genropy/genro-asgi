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

"""Well-known / probe path filter.

Browsers and bots probe a handful of conventional paths on every site
(``/.well-known/*`` per RFC 8615, ``/robots.txt``, ``/sitemap.xml``). When
the site does not expose them, this middleware answers with a clean 404
instead of letting the probe reach the mounted application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import HTTPNotFound
from .base import BaseMiddleware

if TYPE_CHECKING:
    from ..types import Receive, Scope, Send

__all__ = ["WellKnownMiddleware"]


class WellKnownMiddleware(BaseMiddleware):
    """Raise 404 for well-known/probe paths; delegate everything else."""

    middleware_order = 150
    middleware_default = False

    PROBE_PATHS = frozenset({"/robots.txt", "/sitemap.xml"})
    WELL_KNOWN_PREFIX = "/.well-known/"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Raise ``HTTPNotFound`` for a probe path; otherwise delegate to the wrapped app."""
        path = scope.get("path", "/")
        if self._is_probe(path):
            raise HTTPNotFound(f"Not found: {path}")
        await self.app(scope, receive, send)

    def _is_probe(self, path: str) -> bool:
        return path in self.PROBE_PATHS or path.startswith(self.WELL_KNOWN_PREFIX)
