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

"""The ``_server/auth`` container: the mount that holds the auth-method sections.

When the login surface is active the ``ServerApplication`` attaches ONE
``AuthSection`` under the ``auth`` name, so it lives at ``/_server/auth/``.
Each registered auth method (``AuthMethod``) is then attached to this section
under its ``method_id``, so a method's own routes live at
``/_server/auth/<method_id>/`` (e.g. a future OIDC ``start`` and ``callback``
at ``/_server/auth/oidc:google/start``).

The section is a thin router node: it holds no routes of its own, it only
carries the method children and keeps the ordered registry the login surface
reads to build ``login_methods``. The methods are the sections; this is their
mount.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from genro_routes import RoutingClass

if TYPE_CHECKING:
    from ...auth.auth_method import AuthMethod
    from ..server_app import ServerApplication

__all__ = ["AuthSection"]


class AuthSection(RoutingClass):
    """The ``_server/auth`` mount that carries the registered auth methods.

    Note:
        Parent (dual relationship): the ServerApplication, stored as
        ``self.application``. The AsgiServer is reached via
        ``self.application.server``.
    """

    def __init__(self, application: ServerApplication) -> None:
        """Bind the section to its ServerApplication and start an empty registry.

        Args:
            application: The ServerApplication this section belongs to
                (dual relationship). The AsgiServer is ``application.server``.
        """
        self.application = application
        self._methods: dict[str, AuthMethod] = {}

    @property
    def server(self) -> Any:
        """The AsgiServer, reached through the parent ServerApplication."""
        return self.application.server

    @property
    def methods(self) -> dict[str, AuthMethod]:
        """The registered methods, keyed by ``method_id`` (insertion order)."""
        return self._methods

    def register(self, method: AuthMethod) -> None:
        """Attach a method under its ``method_id`` and record it.

        Links the method's router into this section under ``method_id`` (so its
        own routes live at ``/_server/auth/<method_id>/``) and stores it so the
        login surface can enumerate the active methods for ``login_methods``.

        Args:
            method: The AuthMethod to register. Its ``method_id`` must be unique.

        Raises:
            ValueError: If a method with the same ``method_id`` is already
                registered (method ids are unique by contract, so a clash is a
                configuration bug).
        """
        method_id = method.method_id
        if method_id in self.methods:
            raise ValueError(f"auth method already registered: {method_id}")
        self.attach_instance(method, name=method_id)
        self._methods[method_id] = method

    def descriptors(self) -> list[dict[str, Any]]:
        """The descriptor of every registered method, in registration order."""
        return [method.descriptor() for method in self.methods.values()]


if __name__ == "__main__":
    from types import SimpleNamespace

    from ...auth.auth_method import PasswordMethod

    application: Any = SimpleNamespace(server="SERVER")
    section = AuthSection(application)
    assert section.server == "SERVER"
    assert section.descriptors() == []
    method = PasswordMethod(application, "password")
    section.register(method)
    assert section.methods == {"password": method}
    assert section.descriptors() == [method.descriptor()]
    try:
        section.register(PasswordMethod(application, "password"))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on a duplicate method_id")
