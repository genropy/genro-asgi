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

"""Hidden and probe path filter (issue #88).

A path whose first segment starts with a dot is hidden or of service: nothing
of the site lives there, and browsers and bots probe such paths constantly
(``.git``, ``.env``). This middleware answers them with a clean 404 before any
application is reached, and is ON by default. Its one exception is the segment
reserved by RFC 8615: ``/.well-known/<name>`` passes down the chain when
``<name>`` is one of the discovery documents an application declares (the
server read them at mount time, into ``well_known_applications``).

Beside the rule, the fixed probes without a dot (``/robots.txt``,
``/sitemap.xml``) answer 404 as they always did. Switched off, the middleware
filters nothing and every path goes to the demux.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import HTTPNotFound
from ..well_known import HIDDEN_SEGMENT_PREFIX, WELL_KNOWN_SEGMENT
from .base import BaseMiddleware

if TYPE_CHECKING:
    from ..types import Receive, Scope, Send

__all__ = ["WellKnownMiddleware"]


class WellKnownMiddleware(BaseMiddleware):
    """Raise 404 for hidden and probe paths; delegate everything else."""

    middleware_order = 150
    middleware_default = True

    PROBE_PATHS = frozenset({"/robots.txt", "/sitemap.xml"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Raise ``HTTPNotFound`` for a filtered path; otherwise delegate to the wrapped app."""
        path = scope.get("path", "/")
        if path in self.PROBE_PATHS or self.is_hidden(path):
            raise HTTPNotFound(f"Not found: {path}")
        await self.app(scope, receive, send)

    def is_hidden(self, path: str) -> bool:
        """Whether ``path`` is hidden: a dotted first segment naming no served document."""
        segment, _, remainder = path.lstrip("/").partition("/")
        if not segment.startswith(HIDDEN_SEGMENT_PREFIX):
            return False
        if segment != WELL_KNOWN_SEGMENT:
            return True
        return remainder.partition("/")[0] not in self.server.well_known_applications
