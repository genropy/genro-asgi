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

"""DjangoEngineFactory: the one ``django.setup()`` of a group.

The adapter's side of the fork contract. A group whose recipe names an
``engine_factory`` runs a template process: the core instantiates this class
with the recipe's ``engine_kwargs``, calls ``build_group_engine()`` once, and
every worker of the group is a fork of that process — so Django's application
registry is built once for the whole group and the workers find it in their own
memory.

The engine IS Django's WSGI callable: ``get_wsgi_application()`` runs
``django.setup()`` and returns the entry point Django writes in its own
``wsgi.py``. Nothing else is settled here — the hello world has no database and
no lazy scan to pay for — and nothing starts a thread, which the template
requires before it forks.

``DjangoWorker`` builds its engine through this same class when it is spawned
instead of forked: one code path, so the two births cannot diverge.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from django.core.wsgi import get_wsgi_application

__all__ = ["DjangoEngineFactory"]


class DjangoEngineFactory:
    """Builds Django's WSGI callable — the group engine of the fork contract."""

    def __init__(self, *, settings_module: str, project_path: str | None = None) -> None:
        """Args:
        settings_module: the dotted path Django reads its settings from; it is
            written into ``DJANGO_SETTINGS_MODULE``, the one place Django looks.
        project_path: the directory the project's own packages are imported
            from. The worker and the template are children started with
            ``python -m``, so they inherit the environment of the server and
            NOT its ``sys.path``: a project that is not installed reaches them
            only as this value, declared in the recipe.
        """
        self.settings_module = settings_module
        self.project_path = project_path

    def build_group_engine(self) -> Any:
        """The template's one call: Django set up, its WSGI callable returned."""
        if self.project_path and self.project_path not in sys.path:
            sys.path.insert(0, self.project_path)
        os.environ["DJANGO_SETTINGS_MODULE"] = self.settings_module
        return get_wsgi_application()
