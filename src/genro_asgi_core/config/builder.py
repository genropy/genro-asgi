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

"""AsgiConfigBuilder — the ``asgiconfig`` builder dialect (D15).

The user subclasses ``AsgiConfigBuilder`` in a ``config.py`` and overrides
``main(self, root)`` (the recipe). ``ConfigurationHandler`` mounts the builder,
runs the recipe and MATERIALIZES an ``AsgiServer`` by walking the built tree —
unlike the markup dialects (HTML, SVG) there is no renderer: the configuration
is read back directly from the ``SourceBag`` (``node.node_tag`` /
``node.fixed_attr_items()``).

Example ``config.py``::

    from genro_asgi_core.config import AsgiConfigBuilder
    from myshop.app import Application as Shop

    class ServerConfiguration(AsgiConfigBuilder):
        def main(self, root):
            root.server(host="127.0.0.1", port=8000)
            root.middleware(cors=True)
            apps = root.applications(default="shop")
            apps.application(code="shop", app_class=Shop)
"""

from __future__ import annotations

from genro_builders.builder import BuilderBase

from .elements import AsgiConfigElements

__all__ = ["AsgiConfigBuilder"]


class AsgiConfigBuilder(BuilderBase, AsgiConfigElements):
    """Server-configuration dialect: grammar from ``AsgiConfigElements``.

    Carries no renderer — the configuration is walked back out of the built
    ``source`` tree by ``ConfigurationHandler.materialize``.
    """

    _name = "asgiconfig"


if __name__ == "__main__":
    from typing import Any

    from genro_builders.builder import BuilderHandler

    class _Demo(AsgiConfigBuilder):
        def main(self, root: Any) -> None:
            root.server(host="127.0.0.1", port=8000)
            root.middleware(cors=True)
            apps = root.applications(default="shop")
            apps.application(code="shop", app_class=object)

    demo = _Demo(name="config")
    BuilderHandler().add_builder(demo)
    assert [node.node_tag for node in demo.source] == ["server", "middleware", "applications"]
