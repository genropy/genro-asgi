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

"""The ``genro-asgi`` command: boot a server, and manage the named ones.

Usage::

    genro-asgi serve ./config.py                      # a config.py recipe
    genro-asgi serve application=./hello.py:Hello     # one app, no config
    genro-asgi serve application=pkg.mod:App --name demo   # serve AND register
    genro-asgi serve demo                             # relaunch a registered name
    genro-asgi apps                                   # list the registered apps
    genro-asgi stop demo                              # stop a running app
    genro-asgi remove demo                            # drop a registration

The ``serve`` source resolves in this order: an ``application=<target>``
assignment (quickstart — the target class is instantiated with no arguments and
handed to ``AsgiServer(applications=[...])``), an existing ``.py`` path (handed
to ``AsgiServer(config=<absolute path>)``, whose contract is the contrib
handler's own: exactly one ``ConfigBuilder`` subclass defined in the file — this
command ships no loader and lets that error surface), otherwise a NAME looked up
in the registry.

Explicit ``--host``/``--port`` are forwarded as ``AsgiServer`` kwargs: the
server's own "explicit kwarg wins over the configured value" rule does the
precedence, this command computes nothing.

The registry under ``~/.genroasgi`` stores a pointer per name (``apps/<name>.json``:
source and saved options), never a copy of the app, so relaunching by name always
runs the current code. A served name records its pid in ``run/<name>.pid`` so
``apps`` shows what is running and ``stop`` can end it from another shell. A pid
whose process is gone is stale and reads as not running.

``--reload`` runs under uvicorn's reload supervisor, which accepts only an import
string — never a built instance. The source therefore crosses the process
boundary as one JSON object in ``GENRO_ASGI_LAUNCHER``, and ``factory()`` rebuilds
the very same server on every restart. Those two derogations (a module-level
function, state in the environment) are confined to this module.

Exit codes: 0 success, 2 usage errors (argparse), 1 runtime errors — reported as
one line on stderr.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import signal
import sys
from pathlib import Path
from types import ModuleType

import uvicorn

from .asgi_server import AsgiServer
from .config.default_config import DefaultConfig

__all__ = [
    "LAUNCHER_ENV",
    "AppsRegistry",
    "CliError",
    "Cli",
    "ServerLauncher",
    "TargetResolver",
    "factory",
    "main",
]

LAUNCHER_ENV = "GENRO_ASGI_LAUNCHER"
"""The variable carrying the launcher's state across the reload process boundary."""


class CliError(Exception):
    """A runtime error the command reports as one stderr line and exit code 1."""


class AppsRegistry:
    """The ``~/.genroasgi`` store: registered servers and the pids of the running ones.

    The directory is also where a deployment keeps its defaults layer, so
    ``base_dir`` comes from ``DefaultConfig`` — one default for both, one
    ``GENRO_ASGI_HOME`` relocating both, and one parameter a test can point at a
    temporary directory.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.default_config = DefaultConfig(base_dir)
        self.base_dir = self.default_config.base_dir
        self.apps_dir = self.base_dir / "apps"
        self.run_dir = self.base_dir / "run"

    def entry_path(self, name: str) -> Path:
        return self.apps_dir / f"{name}.json"

    def pid_path(self, name: str) -> Path:
        return self.run_dir / f"{name}.pid"

    def save(self, name: str, entry: dict) -> None:
        """Register (or update) *name* with its serve options."""
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        self.entry_path(name).write_text(json.dumps(entry, indent=2), encoding="utf-8")

    def load(self, name: str) -> dict | None:
        """The registration stored for *name*, ``None`` when there is none."""
        path = self.entry_path(name)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def names(self) -> list[str]:
        """The registered names, sorted."""
        if not self.apps_dir.is_dir():
            return []
        return sorted(path.stem for path in self.apps_dir.glob("*.json"))

    def remove(self, name: str) -> bool:
        """Drop *name*'s registration and any leftover pidfile. ``False`` if absent."""
        path = self.entry_path(name)
        if not path.is_file():
            return False
        path.unlink()
        self.clear_pid(name)
        return True

    def write_pid(self, name: str, pid: int) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.pid_path(name).write_text(str(pid), encoding="utf-8")

    def clear_pid(self, name: str) -> None:
        self.pid_path(name).unlink(missing_ok=True)

    def read_pid(self, name: str) -> int | None:
        """The recorded pid IF its process is alive — the file is never trusted.

        A pidfile that is missing, unreadable or names a dead process all read
        the same way: not running.
        """
        path = self.pid_path(name)
        if not path.is_file():
            return None
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            return None
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return None
        return pid


class TargetResolver:
    """Resolves an application target to its class.

    Two spellings: ``package.module:ClassName`` (a plain import) and
    ``path/to/file.py:ClassName`` (a single file, no packaging needed).
    """

    def __init__(self, target: str) -> None:
        self.target = target

    @property
    def parts(self) -> tuple[str, str]:
        """The module part and the class name; a target without ``:`` is an error."""
        module_part, separator, class_name = self.target.partition(":")
        if not (separator and module_part and class_name):
            raise CliError(
                f"application target must be 'package.module:ClassName' or "
                f"'path/to/file.py:ClassName', got {self.target!r}"
            )
        return module_part, class_name

    def resolve(self) -> type:
        """The target class itself."""
        module_part, class_name = self.parts
        if module_part.endswith(".py"):
            module = self.load_file(module_part)
        else:
            module = importlib.import_module(module_part)
        app_class = getattr(module, class_name, None)
        if app_class is None:
            raise CliError(f"{module_part} does not define {class_name!r}")
        return app_class

    def load_file(self, module_part: str) -> ModuleType:
        """Import a single ``.py`` file as a module of its own."""
        path = Path(module_part).resolve()
        if not path.is_file():
            raise CliError(f"application file not found: {path}")
        spec = importlib.util.spec_from_file_location(f"genro_asgi_target_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise CliError(f"cannot load application module: {path}")
        module = importlib.util.module_from_spec(spec)
        # Registered BEFORE exec (importlib contract): the app class must be able
        # to find its own module through ``sys.modules[cls.__module__]``.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


class ServerLauncher:
    """One ``serve`` invocation: resolves its source, builds the server, boots it.

    A source that is neither a quickstart assignment nor an existing ``.py`` file
    is a registered name, adopted at construction: its stored source and options
    replace the ones the command line did not give.
    """

    def __init__(self, options: argparse.Namespace, registry: AppsRegistry) -> None:
        self.registry = registry
        self.source = options.source
        self.name = options.name
        self.host = options.host
        self.port = options.port
        self.reload = options.reload
        if not (self.is_quickstart or self.is_config_path):
            self.adopt_registered(self.source)

    @property
    def is_quickstart(self) -> bool:
        return self.source.startswith("application=")

    @property
    def is_config_path(self) -> bool:
        return self.source.endswith(".py") and Path(self.source).is_file()

    @property
    def entry(self) -> dict:
        """What gets stored under ``--name``: the source and the given options."""
        return {
            "source": self.source,
            "host": self.host,
            "port": self.port,
            "reload": bool(self.reload),
        }

    @property
    def server_kwargs(self) -> dict:
        """The explicitly-given host/port only — an absent key keeps the config's."""
        kwargs: dict = {}
        if self.host is not None:
            kwargs["host"] = self.host
        if self.port is not None:
            kwargs["port"] = self.port
        return kwargs

    @property
    def save_session_path(self) -> str | None:
        """The session snapshot file a NAMED serve arms, ``None`` for a nameless one.

        Giving the instance a name IS the switch: sessions of ``--name demo``
        survive a restart through ``<base_dir>/sessions/demo.pickle``.
        """
        if not self.name:
            return None
        return str(self.registry.base_dir / "sessions" / f"{self.name}.pickle")

    @property
    def constructor_kwargs(self) -> dict:
        """What ``AsgiServer(...)`` receives: host/port plus the armed snapshot."""
        kwargs = dict(self.server_kwargs)
        if self.save_session_path is not None:
            kwargs["save_session"] = self.save_session_path
        return kwargs

    @property
    def quickstart_target(self) -> str:
        """The ``application=`` target, a file spelling made absolute."""
        module_part, class_name = TargetResolver(self.source.partition("=")[2]).parts
        if module_part.endswith(".py"):
            module_part = str(Path(module_part).resolve())
        return f"{module_part}:{class_name}"

    @property
    def launcher_payload(self) -> dict:
        """What ``factory`` needs to rebuild this server in the reloaded process.

        One source key (``application`` or ``config``, always absolute) plus the
        explicitly-given host/port and the armed session snapshot: an absent
        key lets the config's own value apply, exactly as it does here.
        """
        payload = dict(self.constructor_kwargs)
        if self.is_quickstart:
            payload["application"] = self.quickstart_target
        else:
            payload["config"] = str(Path(self.source).resolve())
        return payload

    @property
    def reload_dir(self) -> str:
        """The directory uvicorn watches: the one holding the source file.

        A dotted target has no file of its own to anchor on, so the working
        directory is watched instead.
        """
        module_part = (
            self.quickstart_target.partition(":")[0] if self.is_quickstart else self.source
        )
        if module_part.endswith(".py"):
            return str(Path(module_part).resolve().parent)
        return str(Path.cwd())

    def adopt_registered(self, name: str) -> None:
        """Replace the source and the unset options with the ones stored under *name*."""
        stored = self.registry.load(name)
        if stored is None:
            known = ", ".join(self.registry.names()) or "none registered"
            raise CliError(f"unknown app {name!r} (registered: {known})")
        self.name = self.name or name
        self.source = stored["source"]
        if self.host is None:
            self.host = stored.get("host")
        if self.port is None:
            self.port = stored.get("port")
        if not self.reload:
            self.reload = bool(stored.get("reload"))

    def ensure_importable(self, directory: Path) -> None:
        """Put *directory* on ``sys.path`` so a config.py can import its siblings.

        ``python -m genro_asgi`` puts the working directory there by itself; the
        installed console script does not — without this, ``from hello import
        Hello`` inside a config.py resolves under one invocation and not the
        other.
        """
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))

    def build_server(self) -> AsgiServer:
        """The server this source describes, host/port forwarded when given."""
        if self.is_quickstart:
            app_class = TargetResolver(self.source.partition("=")[2]).resolve()
            return AsgiServer(applications=[app_class()], **self.constructor_kwargs)
        if self.is_config_path:
            config_path = Path(self.source).resolve()
            self.ensure_importable(config_path.parent)
            return AsgiServer(config=str(config_path), **self.constructor_kwargs)
        raise CliError(
            f"cannot serve {self.source!r}: not an existing config.py path, "
            "not an 'application=<target>' assignment"
        )

    def address(self, server: AsgiServer) -> tuple[str, int]:
        """The address this boot binds: the explicit option, else what the server has.

        The same rule ``AsgiServer.serve`` applies — spelled out here because the
        reload supervisor binds by itself and never calls ``serve``.
        """
        host = self.host if self.host is not None else (server.config_host or "127.0.0.1")
        port = self.port if self.port is not None else (server.config_port or 0)
        return host, port

    def run_reloading(self, host: str, port: int) -> None:
        """Boot under uvicorn's reload supervisor, which needs an import string.

        The supervisor imports ``factory`` in a fresh process on every restart,
        so the source travels to it through the environment.
        """
        os.environ[LAUNCHER_ENV] = json.dumps(self.launcher_payload)
        uvicorn.run(
            "genro_asgi.__main__:factory",
            factory=True,
            reload=True,
            reload_dirs=[self.reload_dir],
            host=host,
            port=port,
        )

    def run(self) -> int:
        """Boot the server (blocking), registering the name and its pid first."""
        server = self.build_server()
        if self.name:
            self.registry.save(self.name, self.entry)
            # The pidfile goes down BEFORE uvicorn starts: with --reload this
            # records the supervisor, which is the process ``stop`` must signal.
            self.registry.write_pid(self.name, os.getpid())
        host, port = self.address(server)
        print(f"genro-asgi serving http://{host}:{port}", flush=True)
        try:
            if self.reload:
                self.run_reloading(host, port)
            else:
                server.serve(**self.server_kwargs)
        except KeyboardInterrupt:
            print("Shutdown.")
        finally:
            if self.name:
                self.registry.clear_pid(self.name)
        return 0


class Cli:
    """The command: one parser, one subcommand method each, one exit code."""

    def __init__(self, registry: AppsRegistry | None = None) -> None:
        self.registry = registry or AppsRegistry()

    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="genro-asgi", description="Run and manage ASGI servers.")
        commands = parser.add_subparsers(dest="command", required=True)

        serve = commands.add_parser("serve", help="run a server from a config.py, a target or a name")
        serve.add_argument("source", help="a config.py path, 'application=<target>', or a registered name")
        serve.add_argument("--host", help="bind host (overrides the configured one)")
        serve.add_argument("--port", type=int, help="bind port (overrides the configured one)")
        serve.add_argument("--reload", action="store_true", help="restart on source changes")
        serve.add_argument("--name", help="register the server under this name")
        serve.set_defaults(handler=self.serve)

        commands.add_parser("apps", help="list the registered servers").set_defaults(handler=self.apps)

        stop = commands.add_parser("stop", help="stop a running registered server")
        stop.add_argument("name")
        stop.set_defaults(handler=self.stop)

        remove = commands.add_parser("remove", help="drop a registration")
        remove.add_argument("name")
        remove.set_defaults(handler=self.remove)
        return parser

    def run(self, argv: list[str] | None = None) -> int:
        options = self.parser().parse_args(argv)
        try:
            return options.handler(options)
        except CliError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1

    def serve(self, options: argparse.Namespace) -> int:
        return ServerLauncher(options, self.registry).run()

    def apps(self, options: argparse.Namespace) -> int:
        names = self.registry.names()
        if not names:
            print("No registered servers (register one with: genro-asgi serve <source> --name <name>)")
            return 0
        for name in names:
            entry = self.registry.load(name) or {}
            pid = self.registry.read_pid(name)
            status = f"running (pid {pid})" if pid else "stopped"
            address = f"{entry.get('host') or '-'}:{entry.get('port') or '-'}"
            print(f"{name:<20} {status:<20} {address:<24} {entry.get('source') or '-'}")
        return 0

    def stop(self, options: argparse.Namespace) -> int:
        pid = self.registry.read_pid(options.name)
        if pid is None:
            self.registry.clear_pid(options.name)
            print(f"{options.name}: not running")
            return 0
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            # The process died between the liveness probe and the signal
            # (TOCTOU): same outcome as finding it already stopped.
            self.registry.clear_pid(options.name)
            print(f"{options.name}: not running")
            return 0
        print(f"{options.name}: stopped (pid {pid})")
        return 0

    def remove(self, options: argparse.Namespace) -> int:
        if self.registry.read_pid(options.name) is not None:
            raise CliError(f"{options.name} is running — stop it first")
        if not self.registry.remove(options.name):
            raise CliError(f"{options.name}: not registered")
        print(f"{options.name}: removed")
        return 0


def factory() -> AsgiServer:
    """Rebuild the server described in ``GENRO_ASGI_LAUNCHER``.

    The import-string target of the reload supervisor, and the only module-level
    function here: uvicorn imports it by name in each restarted process, where
    nothing of the parent survives except the environment.
    """
    payload = os.environ.get(LAUNCHER_ENV)
    if payload is None:
        raise CliError(f"{LAUNCHER_ENV} is not set — factory() runs only under 'genro-asgi serve --reload'")
    try:
        described = json.loads(payload)
    except json.JSONDecodeError as error:
        raise CliError(f"{LAUNCHER_ENV} is not valid JSON: {error}") from error
    kwargs = {key: described[key] for key in ("host", "port", "save_session") if key in described}
    if "application" in described:
        return AsgiServer(applications=[TargetResolver(described["application"]).resolve()()], **kwargs)
    if "config" in described:
        # The reloaded process starts fresh: the sibling-import path the parent
        # inserted (ServerLauncher.ensure_importable) must be re-inserted here.
        parent = str(Path(described["config"]).parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        return AsgiServer(config=described["config"], **kwargs)
    raise CliError(f"{LAUNCHER_ENV} carries neither an 'application' nor a 'config' key")


def main(argv: list[str] | None = None) -> int:
    """The ``genro-asgi`` console entry point."""
    return Cli().run(argv)


if __name__ == "__main__":
    sys.exit(main())
