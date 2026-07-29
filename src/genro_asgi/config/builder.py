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
"""

from __future__ import annotations

from genro_builders.contrib.config import ConfigBuilder

from .elements import AsgiServerGrammar

__all__ = ["AsgiConfigBuilder"]


class AsgiConfigBuilder(ConfigBuilder, AsgiServerGrammar):
    """Configuration dialect of genro-asgi: contrib layout + ``AsgiServerGrammar``."""

    _name = "asgiconfig"
