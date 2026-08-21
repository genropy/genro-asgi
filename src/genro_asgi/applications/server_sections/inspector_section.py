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

"""The ``_server/inspector`` section: the SPA pool shown to a human.

Three addresses, one purpose — watching a pool while it works:

    ``/_server/inspector/page``     the page (HTML, from ``resources/``)
    ``/_server/inspector/census``   the whole pool as JSON, per SPA front
    ``/_server/inspector/stream``   the observation stream, as SSE

**Mounting IS the gate.** The ``ServerApplication`` attaches this section only
when ``GNR_ASGI_INSPECTOR`` is set, and no route carries an ``auth_rule``: the
inspector is a collaudo instrument, so it exists where somebody asked for it
and nowhere else.

**It never traverses the hosted site.** No cookie is minted, no connection is
opened, no site path is called: the section reads the commanders' own surfaces
(``get_pool_census``) and their observation stream. An observer that changes
what it observes is useless.

Parent (dual relationship): the ServerApplication, stored as
``self.application``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from genro_routes import RoutingClass, route

from ...sse import SseStream
from ...streaming import StreamingResponse
from ..spa_app_new import SpaApplicationNew

if TYPE_CHECKING:
    from ..server_app import ServerApplication

__all__ = ["InspectorSection", "INSPECTOR_ENV_VAR"]

#: The environment variable whose presence mounts the inspector at all.
INSPECTOR_ENV_VAR = "GNR_ASGI_INSPECTOR"


class InspectorSection(RoutingClass):
    """The ``_server/inspector`` mount: the page, the census, the stream.

    Args:
        application: the ServerApplication this section belongs to — its
            server is where the SPA fronts are found, at call time.
    """

    def __init__(self, application: ServerApplication) -> None:
        self.application = application

    @property
    def spa_fronts(self) -> dict[str, SpaApplicationNew]:
        """The SPA fronts mounted on this server, by application code."""
        return {
            code: mounted
            for code, mounted in self.application.server.applications.items()
            if isinstance(mounted, SpaApplicationNew)
        }

    @route(media_type="text/html")
    def page(self) -> str:
        """The inspector page: the commander above, one row per worker below.

        Note:
            Route: GET /_server/inspector/page
        """
        return (Path(__file__).parent / "resources" / "inspector.html").read_text()

    @route(media_type="application/json")
    async def census(self) -> dict[str, Any]:
        """Every SPA front's whole pool, keyed by application code.

        Note:
            Route: GET /_server/inspector/census
        """
        return {
            code: await front.commander.get_pool_census()
            for code, front in self.spa_fronts.items()
        }

    @route()
    async def stream(self) -> StreamingResponse:
        """The observation stream: one ``census`` event, then every mutation.

        Note:
            Route: GET /_server/inspector/stream
        """
        return SseStream(self.observation_events(), retry_ms=2000).response()

    async def observation_events(self) -> AsyncIterator[dict[str, Any]]:
        """The events the page reads: the opening census, then what the pool reports.

        Subscribes every mounted front's commander on open and unsubscribes all
        of them when the reader goes away — which is what switches the workers'
        reporting off again.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        fronts = self.spa_fronts
        for front in fronts.values():
            await front.commander.subscribe_observation(queue)
        try:
            yield {"event": "census", "data": await self.census()}
            while True:
                yield {"event": "observation", "data": await queue.get()}
        finally:
            for front in fronts.values():
                await front.commander.unsubscribe_observation(queue)
