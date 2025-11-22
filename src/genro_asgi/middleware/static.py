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

from typing import Callable, Any
from pathlib import Path


class StaticFilesMiddleware:
    """Static Files Middleware.

    Serves static files from a directory.
    """

    def __init__(
        self,
        app: Callable,
        directory: str | Path,
        prefix: str = "/static"
    ) -> None:
        """Initialize static files middleware.

        Args:
            app: ASGI application to wrap
            directory: Directory containing static files
            prefix: URL prefix for static files
        """
        self.app = app
        self.directory = Path(directory)
        self.prefix = prefix.rstrip("/")

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable
    ) -> None:
        """ASGI interface.

        Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        # Stub implementation - just pass through to app
        await self.app(scope, receive, send)
