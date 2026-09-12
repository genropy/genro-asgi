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

"""The ready-made configurations, and the shortcut that customises one.

The configuration exists ALWAYS. ``DefaultConfiguration`` is the usual assembly
shipped complete and valid — the listener section, the storage layout and an
empty application collection — and ``CONFIGURATION_TEMPLATES`` names it, so it
can be asked for by name (``AsgiServer(config="default")``, ``genro-asgi serve
template=default``) exactly like a ``config.py`` path.

``ShortcutConfiguration`` is what makes a server composed in code the SAME road
as a server written as a recipe: it is an ordinary recipe whose ``main`` writes
the constructor kwargs it was handed, and it is layered ON TOP of a template by
``AsgiServer``. From the handler down nothing knows which of the two roads was
taken: there is one tree, read through one door.

What the shortcut writes is what the grammar can hold losslessly — the
``server`` scalars, the session ttl, one ``application`` node per instance and
the ``applications`` default. It POPS those kwargs, so the value is read back
from the tree and from nowhere else. What carries a live object
(``session_store``, ``storage``, ``auth``) or a name outside a closed signature
(``middleware``, ``plugins``, whose switches also name classes registered
through ``middleware_registry`` / ``plugin_registry``) has no grammar word and
stays a constructor kwarg; ``applications`` stays too, because the recipe holds
a CLASS and the caller handed instances.
"""

from __future__ import annotations

from typing import Any

from .builder import AsgiConfigBuilder, BaseConfiguration

__all__ = [
    "CONFIGURATION_TEMPLATES",
    "DEFAULT_TEMPLATE",
    "DefaultConfiguration",
    "ShortcutConfiguration",
]


class DefaultConfiguration(BaseConfiguration):
    """The usual assembly, complete and valid: listener, storage, applications.

    ``BaseConfiguration`` brings the shipped defaults (the bare ``server``
    section and the single ``site:`` mount); this adds the empty ``applications``
    collection, so the section a shortcut or a site recipe fills always exists.
    """

    def main(self, root: Any) -> None:
        """The default document: server, storage, applications."""
        cfg = root.configuration()
        self.server_section(cfg)
        self.storage_section(cfg)
        self.applications_section(cfg)

    def applications_section(self, cfg: Any) -> None:
        """The application collection, empty — a site fills it."""
        cfg.applications()


DEFAULT_TEMPLATE = "default"
"""The template a server takes when its caller names none."""

CONFIGURATION_TEMPLATES: dict[str, type] = {DEFAULT_TEMPLATE: DefaultConfiguration}
"""Ready-made configurations by name, for ``config=<name>`` and the CLI."""


class ShortcutConfiguration(AsgiConfigBuilder):
    """The constructor kwargs of a server, written as the top layer of a recipe.

    Built with the kwargs dict itself, which it MUTATES: every option it writes
    into the tree it pops, so the server reads that value back through the
    handler like any other. ``applications`` is left in place — the tree names
    the classes, the caller handed the instances, and the instances are what the
    server mounts.
    """

    server_words = ("host", "port", "external_url", "max_threads", "shutdown_timeout_seconds")
    """The ``server`` attributes a constructor kwarg spells the same way."""

    def __init__(self, kwargs: dict[str, Any], name: str | None = None) -> None:
        super().__init__(name)
        self.server_options = {
            word: kwargs.pop(word) for word in self.server_words if kwargs.get(word) is not None
        }
        self.session_ttl = kwargs.pop("session_ttl", None)
        self.default_code = kwargs.pop("default", None)
        self.app_instances = list(kwargs.get("applications") or ())

    def main(self, root: Any) -> None:
        """The server section the kwargs describe, and one node per application."""
        cfg = root.configuration()
        self.server_section(cfg)
        self.applications_section(cfg)

    def server_section(self, cfg: Any) -> None:
        """The listener words, and the session ttl as the child it belongs to."""
        section = cfg.server(**self.server_options)
        if self.session_ttl is not None:
            section.session(ttl=self.session_ttl)

    def applications_section(self, cfg: Any) -> None:
        """One ``application`` node per instance: its class, its code, its mount.

        The class carries the grammar, so the subtree an application reads its
        own options from (``applications.<code>.request``, and whatever it
        declares) exists for a server composed in code exactly as it does for
        one written as a recipe.
        """
        apps = cfg.applications(default=self.default_code)
        for app in self.app_instances:
            apps.application(code=app.code, mount=app.mount, app_class=type(app))
