"""Settings of the smallest Django site that can hold a session.

No database and no application of its own: the point of the example is the
pool, not Django. The session lives in the process's own memory
(``locmem`` cache), which is exactly why the connection must come back to the
worker that holds it — the visit counter of the view is the proof.
``SECRET_KEY`` is a literal because nothing here signs anything a real
deployment would honour.
"""

SECRET_KEY = "hello-world-example-not-a-secret"
DEBUG = True
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = ["django.contrib.sessions"]
MIDDLEWARE = ["django.contrib.sessions.middleware.SessionMiddleware"]
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
ROOT_URLCONF = "hello_site.urls"
USE_TZ = True
