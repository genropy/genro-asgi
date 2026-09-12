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

"""UserStickyMiddleware: the pool learns who Django logged in.

The project enables it with one line in ``MIDDLEWARE``, below
``django.contrib.auth.middleware.AuthenticationMiddleware`` — it reads the
session and, at a login, ``request.user``, so both must already be there.

**What it watches.** ``_auth_user_id``, the one thing
``django.contrib.auth.login`` and ``logout`` write in and take out of the
session, read once before the request is served and once after. Its appearance
is a login, its disappearance a logout, and a different value is an avatar
switch — three facts of Django's session, which is the layer the pool cannot
see from outside. The signals ``user_logged_in`` / ``user_logged_out`` carry
the same facts and were refused for two reasons: a receiver is connected in a
module-level registry and would have to be armed somewhere other than
``MIDDLEWARE``, which is the one line the issue asks a project for; and the
signal fires in the middle of ``login()``, before Django has written the
session, while the response step sees the request settled.

**How it reaches the worker.** ``DjangoWorker`` puts itself in the environ
under ``WORKER_ENVIRON_KEY`` while it serves, so the middleware finds the
process it runs in without a module-level handle and without the core knowing
anything about Django. An environ with no worker in it is the same project
served by ``manage.py runserver`` — the reference run every Django project
keeps — and there the middleware does nothing.

**Why the response step and not the view.** ``login()`` cycles the session key,
so the connection the pool must own is the one named AFTER the request ran;
declaring it here also puts it in the register before the worker reads the
answer's ``Set-Cookie``, which then finds it already open.
"""

from __future__ import annotations

from typing import Any, Callable

from django.contrib.auth import SESSION_KEY
from django.http import HttpRequest, HttpResponse

from .worker import WORKER_ENVIRON_KEY

__all__ = ["UserStickyMiddleware"]


class UserStickyMiddleware:
    """Tells the worker the user a request logged in, or logged out."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Args:
        get_response: the rest of the chain, as Django hands it over.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Serve the request between two readings of the session's user.

        Args:
            request: the request being served.

        Returns:
            The response, untouched.
        """
        previous_user_id = request.session.get(SESSION_KEY)
        previous_key = request.session.session_key
        response = self.get_response(request)
        self.declare_identity(request, previous_user_id, previous_key)
        return response

    def declare_identity(
        self, request: HttpRequest, previous_user_id: Any, previous_key: str | None
    ) -> None:
        """Say the login or the logout this request turned out to be.

        Args:
            request: the request, served; its session now holds the outcome.
            previous_user_id: ``_auth_user_id`` before the request was served.
            previous_key: the session key before it, which a login replaces and
                a logout throws away — the name the pool knew the connection by.

        A session whose user did not change is every other request, and says
        nothing: the connection is already the pool's, declared by the worker
        from the session cookie.
        """
        worker = request.environ.get(WORKER_ENVIRON_KEY)
        if worker is None:
            return
        user_id = request.session.get(SESSION_KEY)
        if user_id == previous_user_id:
            return
        if user_id is None:
            worker.retire_connection(previous_key)
        else:
            worker.declare_user(request.session.session_key, request.user.get_username())
