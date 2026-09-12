"""The example as a Django application, for the one thing it has to say at boot.

``django.contrib.auth`` connects ``update_last_login`` to ``user_logged_in``,
and that receiver writes a row: it is the only thing Django's own login touches
a database for. This example has no database — the point of it is the pool, not
Django's storage — so the receiver is taken off here, where Django gives every
application its word at the end of ``django.setup()``.
"""

from django.apps import AppConfig


class HelloSiteConfig(AppConfig):
    """The example's application: no model, one disconnection."""

    name = "hello_site"

    def ready(self):
        """Take ``update_last_login`` off the login signal."""
        from django.contrib.auth.models import update_last_login
        from django.contrib.auth.signals import user_logged_in

        user_logged_in.disconnect(update_last_login, dispatch_uid="update_last_login")
