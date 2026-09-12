"""The recipe that serves Wagtail's bakerydemo on the pool.

A real Django site, not a tutorial one: the admin, sessions, a database, images
and static files. The recipe is the hello world's, with two differences and no
third:

- ``CHECKOUT_PATH`` points at a checkout that lives OUTSIDE this repository's
  package tree, under the gitignored ``temp/django_lab/``. Nothing of bakerydemo
  is committed here; the path is a configuration value and the variable
  ``GNR_ASGI_DJANGO_PROJECT`` overrides it for a checkout somewhere else.
- ``settings_module`` is the project's own ``bakerydemo.settings.dev``, which
  keeps ``DEBUG`` on. That is what makes Django serve ``/static/`` and
  ``/media/`` by itself, out of its own urlconf, exactly as it does under
  ``runserver``: the demo needs no static mount of ours and no whitenoise.

The interpreter that runs ``genro-asgi serve`` must import Wagtail, because the
template process and the workers are its children: see ``README.md`` beside this
file for the one command.
"""

import os
import tempfile

from genro_asgi.config import AsgiConfigBuilder
from genro_asgi_multiworker_spa.spa_app import SpaApplication
from genro_asgi_server_app import ServerApplication

#: The bakerydemo checkout, migrated and loaded with its test data.
CHECKOUT_PATH = os.environ.get(
    "GNR_ASGI_DJANGO_PROJECT",
    os.path.abspath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "..",
            "..",
            "temp",
            "django_lab",
            "bakerydemo",
        )
    ),
)
SETTINGS_MODULE = "bakerydemo.settings.dev"

#: Sockets and freezer of this example, kept short: a Unix socket path is capped
#: at about a hundred characters and the worker names are built on top of this.
RUNTIME_DIR = os.path.join(tempfile.gettempdir(), "gnrasgi_django_bakery")


class ServerConfiguration(AsgiConfigBuilder):
    """One listener, one Wagtail site, one pool."""

    def main(self, root):
        cfg = root.configuration()
        cfg.server(host="127.0.0.1", port=8142)
        cfg.middleware()
        self.applications_section(cfg)

    def applications_section(self, cfg):
        """Wagtail answers the site root, through the workers of one group."""
        applications = cfg.applications()
        front = applications.application(
            code="bakery",
            mount="",
            app_class=SpaApplication,
        )
        if os.environ.get("GNR_ASGI_INSPECTOR"):
            # The pool's watching page and its census live on the ``_server``
            # application, and the front attaches them there when that variable
            # is set. The example mounts the host of the section for the same
            # reason and under the same condition.
            applications.application(code="_server", app_class=ServerApplication)
        commander = front.orchestration().commander(
            frozen_users_path=os.path.join(RUNTIME_DIR, "frozen_users"),
            instance_dir=RUNTIME_DIR,
        )
        project = {"settings_module": SETTINGS_MODULE, "project_path": CHECKOUT_PATH}
        commander.groups().group(
            name="pool",
            entry_module="genro_asgi_multiworker_spa.orchestration.worker_entry",
            worker_class="genro_asgi_django.worker:DjangoWorker",
            worker_kwargs=project,
            engine_factory="genro_asgi_django.engine_factory:DjangoEngineFactory",
            engine_kwargs=project,
        )
