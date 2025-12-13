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

"""
Server integration classes for ASGI applications.

This module provides classes that enable applications to integrate with
the AsgiServer and access its resources:

- **ServerBinder**: Controlled interface to server resources
- **AsgiServerEnabler**: Mixin for applications that need server access

Public Exports
==============
::

    __all__ = ["ServerBinder", "AsgiServerEnabler"]
"""

from __future__ import annotations

from typing import Any

__all__ = ["ServerBinder", "AsgiServerEnabler"]


class ServerBinder:
    """
    Controlled interface to access AsgiServer resources.

    Applications receive a ServerBinder (not the server directly) to access
    server-managed resources like configuration, logger, and executors.

    The private ``_server`` attribute provides direct server access for
    advanced use cases.

    Attributes:
        _server: Reference to the AsgiServer (private, for advanced access).

    Example:
        >>> # In an application that inherits AsgiServerEnabler
        >>> config = self.binder.config
        >>> logger = self.binder.logger
        >>> executor = self.binder.executor("pdf", max_workers=2)
    """

    __slots__ = ("_server",)

    def __init__(self, server: Any) -> None:
        """
        Initialize ServerBinder.

        Args:
            server: The AsgiServer instance to bind to.
        """
        self._server = server

    @property
    def config(self) -> Any:
        """
        Server configuration.

        Returns:
            The server's config object (SmartOptions or dict).
        """
        return self._server.config

    @property
    def logger(self) -> Any:
        """
        Server logger.

        Returns:
            The server's logger instance.
        """
        return self._server.logger

    def executor(
        self,
        name: str = "default",
        max_workers: int | None = None,
        initializer: Any = None,
        initargs: tuple[Any, ...] = (),
    ) -> Any:
        """
        Get or create a named executor.

        Args:
            name: Pool identifier (allows multiple isolated pools).
            max_workers: Number of workers (default: CPU count).
            initializer: Function called once per worker at startup.
            initargs: Arguments passed to initializer.

        Returns:
            ExecutorDecorator that can be used as decorator or called directly.
        """
        return self._server.executor(name, max_workers, initializer, initargs)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"ServerBinder(server={self._server.__class__.__name__})"


class AsgiServerEnabler:
    """
    Mixin that enables access to AsgiServer via binder.

    Applications that need server resources should inherit from this mixin.
    When mounted on an AsgiServer, the server automatically sets the ``binder``
    attribute.

    This mixin does NOT define ``__call__`` - the application's own ``__call__``
    is used. This allows combining with external frameworks.

    Attributes:
        binder: ServerBinder instance, set by AsgiServer on mount. None if
                the application is not mounted or used standalone.

    Example:
        >>> class MyApp(AsgiServerEnabler):
        ...     async def __call__(self, scope, receive, send):
        ...         if self.binder:
        ...             self.binder.logger.info("Request received")
        ...         # Handle request...

        >>> # For external frameworks, put AsgiServerEnabler LAST
        >>> class MyStarletteApp(Starlette, AsgiServerEnabler):
        ...     pass  # Starlette's __call__ is used
    """

    binder: ServerBinder | None = None
