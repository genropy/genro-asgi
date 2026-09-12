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

"""DjangoWorker: the core ``SpaWorker`` hosting a Django project.

The execution unit of the Django adapter, and the same shape the genropy
bridge has: the core worker owns the registers, the deposit and the lane to its
commander; this subclass adds the hosted application and one duty of its own.

- Django's WSGI callable is assigned to ``wsgi_app``, the core's consumer seam
  for the http CALL form. The callable is the group engine when this worker was
  forked out of its group's template, and one this worker builds through
  :class:`~genro_asgi_django.engine_factory.DjangoEngineFactory` when it was
  spawned instead — one construction, so the two births cannot diverge.
- The connection is declared from Django's session cookie. The worker serves
  the request through ``serve_django``, reads the session key out of the answer
  (the ``Set-Cookie`` of a session just minted) or out of the request (the
  ``Cookie`` of one that already exists), and calls ``new_connection`` with it
  when this process has never seen it. The core stamps that id on the request's
  slot, the reply carries it back, and the front writes it in the
  ``spa_connection_id`` cookie: from then on the pool sends that session to this
  worker, which is where the session's own memory is.

- Who the user IS, is what Django knows at login, and Django says so through
  :class:`~genro_asgi_django.middleware.UserStickyMiddleware`: the worker puts
  itself in the environ under ``WORKER_ENVIRON_KEY``, the middleware finds it
  there and calls ``declare_user`` at the login and ``retire_connection`` at
  the logout. Both run on the traffic-pool thread, inside the CALL and
  therefore on its slot, which is what the core's login tail reads.

This module imports ``django`` at the top by design: it is loaded through the
``worker_class`` dotted path only where Django is installed.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any, Callable, Iterable

from django.conf import settings

from genro_asgi_multiworker_spa.orchestration import SpaWorker

from .engine_factory import DjangoEngineFactory

__all__ = ["WORKER_ENVIRON_KEY", "DjangoWorker"]

#: The environ key this worker puts itself under, beside the core's
#: ``genro.identity``. It is how a Django middleware — code the project owns,
#: running inside the hosted application — reaches the process it is served by
#: without a module-level handle.
WORKER_ENVIRON_KEY = "genro.spa_worker"


class DjangoWorker(SpaWorker):
    """One worker process serving one Django project."""

    def __init__(
        self,
        name: str,
        *,
        settings_module: str = "",
        project_path: str | None = None,
        group_engine: Any = None,
        **kwargs: Any,
    ) -> None:
        """Args:
        name: the worker's name, the one its handler minted.
        settings_module: the dotted path of the project's settings. Ignored
            when ``group_engine`` arrives: Django is already set up.
        project_path: the directory the project's packages are imported from,
            for the same reason and with the same rule.
        group_engine: the WSGI callable the group's template built, handed to a
            worker born by fork. None when this worker was spawned, and then it
            builds its own through the same factory.
        kwargs: forwarded to ``SpaWorker`` — the spawn grammar and the policies.
        """
        super().__init__(name, **kwargs)
        #: Django's own WSGI callable: the group's, or this worker's own.
        self.django_app: Callable[..., Iterable[bytes]] = group_engine
        if self.django_app is None:
            self.django_app = DjangoEngineFactory(
                settings_module=settings_module, project_path=project_path
            ).build_group_engine()
        #: The cookie Django carries its session key in, as the project named it.
        self.session_cookie_name = settings.SESSION_COOKIE_NAME
        self.wsgi_app = self.serve_django

    def serve_django(
        self, environ: dict[str, Any], start_response: Any
    ) -> Iterable[bytes]:
        """Serve one request through Django and declare the session's connection.

        Args:
            environ: the environ the core's ``WsgiSeam`` built.
            start_response: the seam's own, called with the answer as it comes.

        Returns:
            Django's body iterable, untouched.

        The worker is put in the environ first, so a middleware of the project
        can reach it while the request is being served. The headers are read on
        their way out, because a session born in this request has its key only
        in the ``Set-Cookie`` Django just wrote. The declaration happens on the
        traffic-pool thread, inside the CALL and therefore on its slot, the way
        a hosted site declares its own.
        """
        environ[WORKER_ENVIRON_KEY] = self
        answered: list[tuple[str, str]] = []

        def watching_start_response(
            status: str, headers: list[tuple[str, str]], exc_info: Any = None
        ) -> Any:
            answered.extend(headers)
            return start_response(status, headers, exc_info)

        body = self.django_app(environ, watching_start_response)
        self.declare_connection(environ, answered)
        return body

    def declare_connection(
        self, environ: dict[str, Any], headers: list[tuple[str, str]]
    ) -> None:
        """Open the connection this request's session names, when it is new here.

        Args:
            environ: the request, for the session cookie it came with.
            headers: the answer's headers, for the session cookie it goes out
                with.

        A request that carries no session — nothing written to it, so Django
        mints no key — declares nothing: there is no connection to be sticky to.
        """
        cid = self.get_session_key(environ, headers)
        if cid and cid not in self.connection_register:
            self.new_connection(cid)

    def get_session_key(
        self, environ: dict[str, Any], headers: list[tuple[str, str]]
    ) -> str | None:
        """The session key of one request, the answer's own first.

        Args:
            environ: the request the session cookie may have come in on.
            headers: the answer's headers, where a session just minted — or one
                Django rotated — writes the key that counts from now on.

        Returns:
            The key, or None when this request has no session at all.
        """
        for name, value in headers:
            if name.lower() == "set-cookie":
                morsel = SimpleCookie(value).get(self.session_cookie_name)
                if morsel is not None:
                    return morsel.value
        morsel = SimpleCookie(environ.get("HTTP_COOKIE", "")).get(self.session_cookie_name)
        return morsel.value if morsel is not None else None

    def declare_user(self, cid: str, user_name: str) -> None:
        """The login: the session Django just minted belongs to this user.

        Args:
            cid: the session key the login cycled — the connection's identity
                from now on, and the one the answer's cookie will carry.
            user_name: the name Django logged in.

        Called by the middleware from inside the request, before
        ``declare_connection`` sees the answer: the connection is opened here
        when this process has never seen the key, and ``change_connection_user``
        turns it over to the user on the slot of this very request, which is
        where the core's login tail reads it.
        """
        if cid not in self.connection_register:
            self.new_connection(cid)
        self.change_connection_user(cid, user_name)

    def retire_connection(self, cid: str) -> None:
        """The logout: the connection leaves this worker, and its user with it.

        Args:
            cid: the session key the logout is flushing away.

        The core has no way back to nobody — ``change_connection_user`` refuses
        a guest as a target — so the row goes instead: the cascade announces the
        connection and, when it was his last, the user. A key this process does
        not hold is nothing to retire and nothing to complain about: the browser
        may have been served by another worker before.
        """
        item = self.connection_register.get(cid)
        if item is not None:
            self.drop_connection(item["user"], cid)
