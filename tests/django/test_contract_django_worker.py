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

"""Contract: a Django project hosted by a worker, and the connection its session opens.

The Django here is the real one, on the real example project
(``contrib/django/examples/hello_world``): what is doubled is only the wire
above the worker, which a unit test gives it through ``attach_wire``.

Three facts are held: the worker serves what the group's template built when it
was forked, and builds the same thing itself when it was not; a request whose
session Django minted opens a connection named by the session key, once; a
request with no session opens nothing.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
import sys

import pytest

from genro_asgi_multiworker_spa.orchestration import FreezeHandler

from tests.spa.orchestration.conftest import attach_wire

EXAMPLE_PATH = str(
    Path(__file__).resolve().parents[2] / "contrib" / "django" / "examples" / "hello_world"
)
SETTINGS_MODULE = "hello_site.settings"
WORKER_NAME = "django_0001"


@pytest.fixture(scope="module")
def django_engine():
    """Django set up once, the way the group's template does it."""
    from genro_asgi_django.engine_factory import DjangoEngineFactory

    engine = DjangoEngineFactory(
        settings_module=SETTINGS_MODULE, project_path=EXAMPLE_PATH
    ).build_group_engine()
    yield engine
    sys.path.remove(EXAMPLE_PATH)


@pytest.fixture
def worker(tmp_path, django_engine):
    """A forked worker's shape: the engine handed in, a stub wire, a slot."""
    from genro_asgi_django.worker import DjangoWorker

    worker = DjangoWorker(
        WORKER_NAME,
        freeze_handler=FreezeHandler(tmp_path / "frozen_users"),
        group_engine=django_engine,
    )
    attach_wire(worker)
    yield worker
    worker.exit_process()


def http_call(path: str = "/", cookie: str | None = None) -> dict[str, Any]:
    """The http CALL form as the front packs it, with or without our cookie."""
    headers = [["host", "hello.example:8131"]]
    if cookie:
        headers.append(["cookie", cookie])
    return {
        "http": {
            "method": "GET",
            "path": path,
            "query_string": "",
            "headers": headers,
            "body": b"",
            "client": ["127.0.0.1", 51234],
            "scheme": "http",
            "cid": None,
        },
        "identity": None,
    }


def session_cookie(served: dict[str, Any]) -> str:
    """The session cookie the answer carries, as a browser would send it back."""
    for name, value in served["headers"]:
        if name.lower() == "set-cookie" and value.startswith("sessionid="):
            return f"sessionid={SimpleCookie(value)['sessionid'].value}"
    raise AssertionError(f"no session cookie in {served['headers']}")


class TestTheWorkerHostsDjango:
    async def test_the_hosted_application_answers(self, worker) -> None:
        served = await worker._serve_request(http_call())
        assert served["status"] == 200
        assert served["body"] == b"hello world\nvisits: 1\n"

    def test_a_forked_worker_serves_the_engine_it_was_handed(
        self, worker, django_engine
    ) -> None:
        assert worker.django_app is django_engine

    def test_a_spawned_worker_builds_its_own(self, tmp_path, django_engine) -> None:
        from genro_asgi_django.worker import DjangoWorker

        worker = DjangoWorker(
            WORKER_NAME,
            freeze_handler=FreezeHandler(tmp_path / "frozen_users"),
            settings_module=SETTINGS_MODULE,
            project_path=EXAMPLE_PATH,
        )
        try:
            assert worker.django_app is not None and worker.django_app is not django_engine
            assert worker.wsgi_app == worker.serve_django
        finally:
            worker.exit_process()


class TestTheConnectionIsDeclaredFromTheSession:
    async def test_a_new_session_opens_the_connection_it_names(self, worker) -> None:
        served = await worker._serve_request(http_call())
        cid = session_cookie(served).partition("=")[2]
        assert list(worker.connection_register.keys()) == [cid]
        assert served["connection_id"] == cid

    async def test_the_same_session_is_declared_once(self, worker) -> None:
        first = await worker._serve_request(http_call())
        cookie = session_cookie(first)
        second = await worker._serve_request(http_call(cookie=cookie))
        assert second["body"] == b"hello world\nvisits: 2\n"
        assert list(worker.connection_register.keys()) == [cookie.partition("=")[2]]

    async def test_a_request_with_no_session_declares_nothing(self, worker) -> None:
        served = await worker._serve_request(http_call(path="/nothing-here"))
        assert served["status"] == 404
        assert list(worker.connection_register.keys()) == []
