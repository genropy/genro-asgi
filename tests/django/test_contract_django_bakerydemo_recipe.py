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

"""Contract: the bakerydemo recipe names a checkout that is not in this tree.

The project itself is Wagtail's demo, checked out under the repository's
gitignored ``temp/django_lab/`` and never committed here, so the suite holds
what the recipe says and not what the site answers: the live proof is the
demonstration through ``genro-asgi serve``, recorded in the subtask.

What the recipe must keep saying: the same two words as the hello world, the
checkout as a path the environment can move, and the project's own settings
module — the one that keeps ``DEBUG`` on and therefore makes Django serve
``/static/`` and ``/media/`` out of its own urlconf.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from genro_asgi import AsgiServer, ConfigurationHandler
from genro_asgi_multiworker_spa.spa_app import SpaApplication

EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2] / "contrib" / "django" / "examples" / "bakerydemo"
)
CONFIG_PATH = EXAMPLE_PATH / "config.py"
CHECKOUT_PATH = "/somewhere/else/bakerydemo"


@pytest.fixture
def recipe(monkeypatch):
    """The ``ServerConfiguration`` of the example, with the checkout declared."""
    monkeypatch.setenv("GNR_ASGI_DJANGO_PROJECT", CHECKOUT_PATH)
    monkeypatch.delenv("GNR_ASGI_INSPECTOR", raising=False)
    spec = importlib.util.spec_from_file_location("xt_bakerydemo_config", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ServerConfiguration


class TestTheBakerydemoRecipe:
    def test_it_builds_a_server_with_the_spa_front_on_the_root(self, recipe) -> None:
        server = AsgiServer(config=recipe)

        assert isinstance(server.applications["bakery"], SpaApplication)
        assert server.applications["bakery"].mount == ""

    def test_the_group_names_the_django_worker_and_its_engine_factory(self, recipe) -> None:
        group = ConfigurationHandler(recipe).group_kwargs("bakery")["pool"]

        assert group["worker_class"] == "genro_asgi_django.worker:DjangoWorker"
        assert group["engine_factory"] == "genro_asgi_django.engine_factory:DjangoEngineFactory"

    def test_the_checkout_travels_as_configuration(self, recipe) -> None:
        group = ConfigurationHandler(recipe).group_kwargs("bakery")["pool"]
        project = {
            "settings_module": "bakerydemo.settings.dev",
            "project_path": CHECKOUT_PATH,
        }

        assert group["worker_kwargs"] == {**project, "group": "pool"}
        assert group["engine_kwargs"] == project
