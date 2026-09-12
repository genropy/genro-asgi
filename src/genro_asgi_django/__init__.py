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

"""The Django adapter: a Django project served by the multiworker pool.

Two classes and no application of its own — a Django project takes the road
genropy takes, which is the pool:

- :class:`~genro_asgi_django.worker.DjangoWorker`, the worker that hosts the
  project and declares the connection from Django's session cookie;
- :class:`~genro_asgi_django.engine_factory.DjangoEngineFactory`, the one
  ``django.setup()`` of a group, run in its template process.

Both are named in the recipe, as dotted paths, on the group element — nothing
here is imported by the core. Beside them and imported by neither:

- :class:`~genro_asgi_django.middleware.UserStickyMiddleware`, the line a
  project adds to its own ``MIDDLEWARE`` so the pool learns who logged in. It
  is left out of this module on purpose: it imports ``django.contrib.auth``,
  and the recipe reaches the factory through this package before
  ``django.setup()`` has run.

The example project and the recipe that serves it live in
``contrib/django/examples/hello_world/``.

Importing this package imports Django.
"""

from .engine_factory import DjangoEngineFactory
from .worker import DjangoWorker

__all__ = ["DjangoEngineFactory", "DjangoWorker"]
