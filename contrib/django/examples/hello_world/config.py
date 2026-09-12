"""The recipe that serves the Django hello world on the pool.

``genro-asgi serve ./config.py`` from this directory. One listener, one spa
front on the site root, one group of workers whose child is the Django adapter:

- ``worker_class`` is the worker that hosts the project and declares the
  connection from Django's session cookie;
- ``engine_factory`` is the class the group's template process builds Django
  with, once for the whole group, and every worker is a fork of it;
- ``settings_module`` and ``project_path`` are the only two words the project
  needs. The template and the workers are children started with ``python -m``:
  they inherit the server's environment and not its ``sys.path``, so the
  directory this file lives in is declared here as a value.

Everything is in this document and nothing in a constructor kwarg or an
environment variable of its own.
"""

import os
import tempfile

from genro_asgi.config import AsgiConfigBuilder
from genro_asgi_multiworker_spa.spa_app import SpaApplication
from genro_asgi_server_app import ServerApplication

PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))
SETTINGS_MODULE = "hello_site.settings"

#: The sockets and the freezer of this example: short paths under the system
#: temp directory, because a Unix socket path is capped at about a hundred
#: characters and the worker names are built on top of this one.
RUNTIME_DIR = os.path.join(tempfile.gettempdir(), "gnrasgi_django_hello")


class ServerConfiguration(AsgiConfigBuilder):
    """One listener, one Django project, one pool."""

    def main(self, root):
        cfg = root.configuration()
        cfg.server(host="127.0.0.1", port=8131)
        cfg.middleware()
        self.applications_section(cfg)

    def applications_section(self, cfg):
        """Django answers the site root, through the workers of one group."""
        applications = cfg.applications()
        front = applications.application(
            code="hello",
            mount="",
            app_class=SpaApplication,
        )
        if os.environ.get("GNR_ASGI_INSPECTOR"):
            # The pool's watching page and its census live on the ``_server``
            # application, and the front attaches them there when that variable
            # is set. The example mounts the host of the section for the same
            # reason and under the same condition: looking at the pool is asked
            # for by name, so the hello world has one application without it.
            applications.application(code="_server", app_class=ServerApplication)
        commander = front.orchestration().commander(
            frozen_users_path=os.path.join(RUNTIME_DIR, "frozen_users"),
            instance_dir=RUNTIME_DIR,
        )
        project = {"settings_module": SETTINGS_MODULE, "project_path": PROJECT_PATH}
        commander.groups().group(
            name="pool",
            entry_module="genro_asgi_multiworker_spa.orchestration.worker_entry",
            worker_class="genro_asgi_django.worker:DjangoWorker",
            worker_kwargs=project,
            engine_factory="genro_asgi_django.engine_factory:DjangoEngineFactory",
            engine_kwargs=project,
        )
