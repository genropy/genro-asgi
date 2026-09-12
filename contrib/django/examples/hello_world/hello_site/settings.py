"""Settings of the smallest Django site that can hold a session and a login.

No database and no application of its own: the point of the example is the
pool, not Django. The session lives in the process's own memory
(``locmem`` cache), which is exactly why the connection must come back to the
worker that holds it — the visit counter of the view is the proof. The users
are two literals in ``hello_site.auth``, for the same reason: a login is a fact
of Django's session, and where the names come from changes nothing about it.
``SECRET_KEY`` is a literal because nothing here signs anything a real
deployment would honour.
"""

SECRET_KEY = "hello-world-example-not-a-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "hello_site.apps.HelloSiteConfig",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # The one line a project adds so the pool learns who logged in. It goes
    # below the two above: it reads the session, and the user they put there.
    "genro_asgi_django.middleware.UserStickyMiddleware",
]
AUTHENTICATION_BACKENDS = ["hello_site.auth.LiteralUserBackend"]
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
DATABASES = {}
ROOT_URLCONF = "hello_site.urls"
USE_TZ = True
