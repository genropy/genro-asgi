# Django on the multiworker pool

The adapter is the `genro_asgi_django` package, under `src/`: a Django project
takes the road genropy takes, which is the pool, and nothing of it lives here.

What lives here are the examples. `examples/hello_world/` is one view, one
settings module and one recipe. Serve it with

```
cd examples/hello_world
genro-asgi serve ./config.py
```

`examples/bakerydemo/` is the real site: Wagtail's demo bakery, on a checkout
you make yourself outside this tree. Its own README carries the commands.

The guide — what the two classes do, how the connection is declared, and how to
verify it — is `docs/guides/django.md`.
