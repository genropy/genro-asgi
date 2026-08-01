# The `genro-asgi` command

> **Status:** 🔴 DA REVISIONARE

## What it does

Installing the package puts a `genro-asgi` command on your path. It boots a
server without you writing an entry point, and it keeps a small registry of
named servers so you can start, list and stop them from any shell.

```
genro-asgi serve <source> [--host H] [--port P] [--reload] [--name N]
genro-asgi apps
genro-asgi stop <name>
genro-asgi remove <name>
```

Everything lives in `genro_asgi/__main__.py`; the server core knows nothing
about it. `python3 -m genro_asgi ...` is the same command, useful when the
console script is not on the path.

## When to use it

Use it for development and for a container `CMD`: a `config.py` plus
`genro-asgi serve` is a complete deployment unit, no `main.py` to maintain. Keep
writing your own Python entry point when the process must do something around
the server — build objects the config cannot express, run migrations first, or
embed the server in a larger program. `.serve()` remains the programmatic way in
and the command adds nothing you cannot do by hand.

## Setup

Nothing to arm. The command ships with the package, and uvicorn — which it boots
under — is already a dependency.

## Serving from a `config.py`

The primary form. A source that is an **existing `.py` path** is handed to
`AsgiServer(config=...)`. Two files in one directory — the application and the
recipe that serves it:

```python
# hello.py
from genro_asgi import RoutedApplication
from genro_routes import route


class Hello(RoutedApplication):
    mount = ""

    @route()
    def greet(self, name: str = "world") -> dict[str, str]:
        return {"hello": name}
```

```python
# config.py
from genro_asgi.config import AsgiConfigBuilder

from hello import Hello


class ServerConfiguration(AsgiConfigBuilder):
    def main(self, root):
        cfg = root.configuration()
        cfg.server(host="127.0.0.1", port=8123)
        cfg.applications().application(code="hello", app_class=Hello)
```

What a recipe can contain — the sections, the resolvers that keep secrets out of
it, and how the server reads it back — is the subject of
[Configuration](configuration.md).

The command puts the config file's own directory on `sys.path` before loading
it, so `from hello import Hello` resolves regardless of how the command is
invoked or from where.

```
$ genro-asgi serve ./config.py
genro-asgi serving http://127.0.0.1:8123
INFO:     Started server process [72897]
INFO:     Application startup complete.
```

The contract on that file is **the config handler's own**, not the command's:
"must define exactly one `ConfigBuilder` subclass" — in a genro-asgi recipe
that subclass is `AsgiConfigBuilder`. The command ships no loader of its own,
so a recipe error surfaces as the same boot error you get from
`AsgiServer(config=...)` in a script.

## Serving one application, no config

For a quick run there is the `application=` form, which resolves a class and
hands it to `AsgiServer(applications=[...])` — instantiated with no arguments:

```
$ genro-asgi serve application=./hello.py:Hello --port 8124
genro-asgi serving http://127.0.0.1:8124
```

Two spellings are accepted after `application=`:

- `package.module:ClassName` — a plain import, for an installed or importable
  module;
- `path/to/file.py:ClassName` — a single file, loaded directly, no packaging
  needed.

A target without the `:` separator is an error naming both forms.

`--host` and `--port` are **forwarded as `AsgiServer` kwargs**. The server's own
rule does the precedence — an explicit kwarg wins over the configured value,
wholesale per kwarg — and the command computes nothing.

## The registry of named servers

`--name` registers the server under that name and records its pid, so other
shells can see and stop it:

```
$ genro-asgi serve ./config.py --name demo
$ genro-asgi apps
demo                 running (pid 72897)  -:-                      ./config.py
$ genro-asgi stop demo
demo: stopped (pid 72897)
$ genro-asgi apps
demo                 stopped              -:-                      ./config.py
$ genro-asgi remove demo
demo: removed
```

A registered name then becomes a source of its own — `genro-asgi serve demo`
relaunches with the stored options — and an unknown name is an error listing the
names that do exist.

**Naming an instance also arms the session snapshot**: the sessions of
`--name demo` are pickled to `~/.genroasgi/sessions/demo.pickle` at shutdown
and reloaded at the next boot (expired ones filtered out by their TTL). A
nameless serve stays volatile. This is a development convenience — production
deployments will bring their own persistence. See the
[sessions guide](sessions.md) for details.

The store is `~/.genroasgi`: `apps/<name>.json` holds the **pointer** (the
source string and the options you gave), `run/<name>.pid` the pid of the running
process. It never copies your application, so relaunching by name always runs the
current code. `stop` sends `SIGTERM`; `remove` refuses to drop a registration
while it is running and tells you to stop it first.

**A pidfile is never trusted.** Missing, unreadable, or naming a process that no
longer exists — all three read the same way: not running. A crashed server
therefore shows as `stopped` rather than as a phantom, and `stop` cleans the
stale file up.

## Reloading on source changes

```
$ genro-asgi serve ./config.py --reload --name demo
```

uvicorn's reload supervisor accepts **only an import string**, never a built
server instance: it starts a fresh process on every restart, and nothing of the
parent survives into it. So the command passes it
`genro_asgi.__main__:factory` and sends the description of the server across the
process boundary in one environment variable, **`GENRO_ASGI_LAUNCHER`** — a JSON
object carrying one source key (`config` or `application`, always an absolute
path) plus `host`/`port` *only when you gave them explicitly*, so an absent key
still lets the config's own value apply. `factory()` reads it and rebuilds the
very same server each time.

You never set `GENRO_ASGI_LAUNCHER` yourself; called outside the launcher,
`factory()` says so and stops. The watched directory is the one holding the
source file (a dotted target has no file to anchor on, so the working directory
is watched instead).

The pidfile written under `--name` records the **supervisor**, which is the
process `stop` must signal — the supervisor honours `SIGTERM` and takes its
child down with it, so `stop` behaves identically with and without `--reload`.

## How to verify it

With the `hello.py` above — a `RoutedApplication` with a `greet` route — in the
current directory:

```
$ genro-asgi serve application=./hello.py:Hello --port 8124 --name quick
genro-asgi serving http://127.0.0.1:8124

$ curl -s 'http://127.0.0.1:8124/greet?name=cli'
{"hello":"cli"}

$ genro-asgi apps
quick                running (pid 75171)  -:8124                   application=./hello.py:Hello

$ genro-asgi stop quick
quick: stopped (pid 75171)
```

## Gotchas

- **`apps` shows the options you gave, not the address in use.** The registry
  stores the command line, so a host or port that came from the `config.py`
  prints as `-`. The line the server prints on boot
  (`genro-asgi serving http://...`) is the address it actually bound.
- **A relative source is resolved against the shell you serve from.** It is
  stored in the registry as you typed it, so `genro-asgi serve demo` from a
  different directory will not find a relative `./config.py`. Register with an
  absolute path if you plan to relaunch from elsewhere.
- **No `--workers`.** Multi-process supervision is genro-juggler's job, not this
  command's. There is no `--debug` either.
- **Exit codes:** `0` success, `2` argparse usage errors, `1` runtime errors —
  reported as one line on stderr.
- **`--reload` is a development tool.** It costs a supervisor process and a file
  watcher; do not ship it in a container image.
