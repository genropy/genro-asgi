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

"""AsgiConfigBuilder — the ``asgiconfig`` dialect: contrib/config + the server's grammar.

The dialect is the contrib configuration builder (``ConfigBuilder``: the
``configuration`` root, the four-layer read contract, the XML render) composed
with the grammar the server class declares (``AsgiServer.grammar``). A site
subclasses it in a ``config.py`` and overrides ``main(self, root)``; the runtime
reads the built tree through ``ConfigurationHandler`` and nothing else.

Recipes orchestrate in ``main`` and delegate each section to a method taking the
PARENT node, so a section stays small enough to read at a glance::

    from genro_asgi.config import AsgiConfigBuilder
    from myshop.app import Application as Shop

    class ServerConfiguration(AsgiConfigBuilder):
        def main(self, root):
            cfg = root.configuration()
            self.server_section(cfg)
            cfg.applications(default="shop").application(code="shop", app_class=Shop)

        def server_section(self, cfg):
            '''The listener and the session TTL.'''
            cfg.server(host="127.0.0.1", port=8000).session(ttl=3600)

``BaseConfiguration`` ships the package's OWN defaults in the same form — a
recipe, not a dict of fallbacks. Every handler the server builds layers it
under the site's recipe, so a site inherits what it does not say; deviating
means overriding one hook method.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genro_bag import BagResolver
from genro_builders.contrib.config import ConfigBuilder
from genro_storage import StorageManager

from ..storage_mixin import DEFAULT_SITE_MOUNT
from .elements import AsgiServerGrammar

__all__ = ["AsgiConfigBuilder", "BaseConfiguration"]


class AsgiConfigBuilder(ConfigBuilder, AsgiServerGrammar):
    """Configuration dialect of genro-asgi: contrib layout + ``AsgiServerGrammar``."""

    _name = "asgiconfig"

    default_config: bool | str | Path | None = None
    """Where this recipe's defaults layer comes from — ``DefaultConfig`` resolves it.

    ``None`` (the default) takes the conventional ``<base_dir>/config.py`` when
    that file exists; ``False`` means no defaults layer at all; a path names the
    file, and a missing one is a ``ConfigError``. The recipe governs its own
    inheritance — the server takes no kwarg for it.
    """


class BaseConfiguration(AsgiConfigBuilder):
    """The package's shipped defaults, AS A RECIPE — the lowest layer of every site.

    ``ConfigurationHandler`` layers it under the optional defaults recipe and the
    site's own (``DefaultConfig.parents_for()``), so the defaults are *executed*
    through the grammar like any other recipe instead of being reproduced as
    constructor fallbacks. A site deviates by overriding ONE hook and nothing
    else — ``storage_key`` for the key material, ``storage_mounts`` for the
    layout, ``server_section`` for the listener::

        from genro_bag.resolvers import EnvResolver

        class ServerConfiguration(BaseConfiguration):
            storage_key = EnvResolver("GENRO_STORAGE_KEY")

            def storage_mounts(self, section):
                section.local(name="site", base_path="/srv/shop")
                section.s3(name="uploads", bucket="shop-media")

    A recipe that subclasses ``AsgiConfigBuilder`` directly inherits the same
    defaults: the layering is the handler's, not the class hierarchy's.
    """

    storage_key: str | BagResolver | None = None
    """At-rest key material of the storage section — a site sets it to a resolver."""

    def main(self, root: Any) -> None:
        """The default document: the server section and the storage section."""
        cfg = root.configuration()
        self.server_section(cfg)
        self.storage_section(cfg)

    def server_section(self, cfg: Any) -> None:
        """The ``server`` section, bare — the hook a machine or site recipe overrides.

        It declares no value on purpose, and there is no signature default to
        inherit either: the element's four parameters are all ``None``, which the
        read stack reads as absent. The listener defaults stay where they live —
        in the constructor.
        """
        cfg.server()

    def storage_section(self, cfg: Any) -> None:
        """The ``storage`` section: genro-storage's mount point plus the key material."""
        self.storage_mounts(cfg.storage(app=StorageManager, storage_key=self.storage_key))

    def storage_mounts(self, section: Any) -> None:
        """The default layout: one ``site:`` mount on the deployment directory.

        The mount is ``DEFAULT_SITE_MOUNT`` written as a recipe line — the tag IS
        its ``protocol`` — so the layout the mixin builds without a recipe and the
        layout this recipe declares cannot drift apart.

        The anchor is the cwd read WHEN THE RECIPE RUNS, which is boot: the same
        recipe follows whatever directory the deployment starts from. It is
        written absolute because genro-storage's local backend rejects a
        relative ``base_path`` string outright.
        """
        section.local(name=DEFAULT_SITE_MOUNT["name"], base_path=str(Path.cwd()))
