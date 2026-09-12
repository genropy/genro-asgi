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

"""Contract: the hello world recipe builds a server, and its group names the adapter.

Construction only — the pool is built by the lifespan, and the live proof of
this recipe is the demonstration through ``genro-asgi serve``. What is held
here is that the one document says everything: the spa front on the root, the
Django worker and the Django engine factory as the group's child, and the two
words of the project as configuration values rather than kwargs of a
constructor.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from genro_asgi import AsgiServer, ConfigurationHandler
from genro_asgi_multiworker_spa.spa_app import SpaApplication

EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "contrib" / "django" / "examples" / "hello_world"
CONFIG_PATH = EXAMPLE_PATH / "config.py"


@pytest.fixture(scope="module")
def recipe():
    """The ``ServerConfiguration`` of the example, loaded from its own file."""
    spec = importlib.util.spec_from_file_location("xt_hello_world_config", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ServerConfiguration


class TestTheHelloWorldRecipe:
    def test_it_builds_a_server_with_the_spa_front_on_the_root(self, recipe) -> None:
        server = AsgiServer(config=recipe)

        assert isinstance(server.applications["hello"], SpaApplication)
        assert server.applications["hello"].mount == ""

    def test_the_group_names_the_django_worker_and_its_engine_factory(self, recipe) -> None:
        group = ConfigurationHandler(recipe).group_kwargs("hello")["pool"]

        assert group["worker_class"] == "genro_asgi_django.worker:DjangoWorker"
        assert group["engine_factory"] == "genro_asgi_django.engine_factory:DjangoEngineFactory"

    def test_the_project_travels_as_configuration(self, recipe) -> None:
        group = ConfigurationHandler(recipe).group_kwargs("hello")["pool"]
        project = {"settings_module": "hello_site.settings", "project_path": str(EXAMPLE_PATH)}

        # The reader adds the group's own name to what the worker is built
        # with: the child knows which group it serves in.
        assert group["worker_kwargs"] == {**project, "group": "pool"}
        assert group["engine_kwargs"] == project
