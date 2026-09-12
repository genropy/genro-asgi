# Wagtail's bakerydemo on the pool

A real Django site — the admin, sessions, a database, images, static files and
search — served by the multiworker pool with the hello world's recipe shape and
no adapter of its own.

Nothing of bakerydemo is committed here: `config.py` points at a checkout you
make yourself.

## The checkout

```
mkdir -p <repo>/temp/django_lab && cd <repo>/temp/django_lab
git clone https://github.com/wagtail/bakerydemo
cd bakerydemo
cp bakerydemo/settings/local.py.example bakerydemo/settings/local.py
cp .env.example .env
```

## The interpreter

The template process and the workers are children of `genro-asgi serve`, started
with `python -m` and the parent's environment: **the interpreter that runs
`genro-asgi serve` must import Wagtail.** bakerydemo pins `Django>=6.0,<6.1`, so
it does not share this repository's own virtual environment; give the lab one of
its own.

```
cd <repo>/temp/django_lab
uv venv .venv --python 3.12
VIRTUAL_ENV=$PWD/.venv uv pip install -r bakerydemo/requirements/development.txt
VIRTUAL_ENV=$PWD/.venv uv pip install -e <repo>
```

Then the project's own two commands, from the checkout:

```
cd <repo>/temp/django_lab/bakerydemo
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py load_initial_data
```

## Serving it

```
cd <repo>/contrib/django/examples/bakerydemo
GNR_ASGI_INSPECTOR=1 \
GNR_ASGI_DJANGO_PROJECT=<repo>/temp/django_lab/bakerydemo \
  <repo>/temp/django_lab/.venv/bin/genro-asgi serve ./config.py
```

The site is on <http://127.0.0.1:8142/>, the admin on
<http://127.0.0.1:8142/admin/> with `admin` / `changeme`, and the census of the
pool on <http://127.0.0.1:8142/_server/inspector/census>.

`GNR_ASGI_DJANGO_PROJECT` overrides the checkout path. Without it the recipe
looks for `temp/django_lab/bakerydemo` beside the directory the recipe's own
four parents lead to — which is the repository when the recipe is served from a
plain clone, and not the repository when it is served from a git worktree.

## Who logged in

The pool learns the user from one line the project adds to its own `MIDDLEWARE`.
bakerydemo's is in `bakerydemo/settings/local.py`, the file the checkout step
copies from its example:

```python
from .base import MIDDLEWARE

MIDDLEWARE = MIDDLEWARE + ["genro_asgi_django.middleware.UserStickyMiddleware"]
```

It must come after `django.contrib.auth.middleware.AuthenticationMiddleware`,
which the base settings already declare. Log in at `/admin/` as `admin` /
`changeme` and the census answers `"connection_user_map": {"<session>": "admin"}`
and `"user_worker_map": {"admin": "pool_0001"}` where it answered `guest_…`
before; log out and the connection leaves, the user with it when it was his
last. The guide's *Who logged in* section carries the whole transcript.

## Static and media

Neither is mounted by this server: `bakerydemo.settings.dev` keeps `DEBUG` on,
and the project's own `urls.py` adds `staticfiles_urlpatterns()` and
`static(MEDIA_URL, ...)` under that condition. So `/static/` and `/media/` are
Django views like every other URL, served through the pool's workers, and they
answer byte for byte what `runserver` answers. A deployment turning `DEBUG` off
serves both the way it would behind any WSGI server — whitenoise in the
project's own middleware, or a web server in front — and the pool changes
nothing about that choice.
