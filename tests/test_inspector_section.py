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

"""The ``_server/inspector`` section: mounted by the env var, and by nothing else.

Contract: the mount IS the gate — without ``GNR_ASGI_INSPECTOR`` the section
does not exist at all; with it the page is HTML and the census is JSON. And in
neither case does the inspector touch the hosted site: no ``sticky_cid`` cookie
ever comes back from it.
"""

from __future__ import annotations

import json

import pytest

from genro_asgi import AsgiServer, BaseApplication
from genro_asgi.applications.server_sections import INSPECTOR_ENV_VAR


@pytest.fixture
def inspector_server(monkeypatch):
    """A server whose ``_server`` app was built with the inspector switched on."""
    monkeypatch.setenv(INSPECTOR_ENV_VAR, "1")
    return AsgiServer(applications=[BaseApplication(mount="")])


@pytest.fixture
def plain_server(monkeypatch):
    """A server built with the inspector switched off: the section is not there."""
    monkeypatch.delenv(INSPECTOR_ENV_VAR, raising=False)
    return AsgiServer(applications=[BaseApplication(mount="")])


async def test_without_the_env_var_the_page_is_not_there(
    plain_server, http_request, response_status
):
    sent = await http_request(plain_server, "/_server/inspector/page")

    assert response_status(sent) == 404


async def test_the_page_is_html(
    inspector_server, http_request, response_status, response_headers, response_body
):
    sent = await http_request(inspector_server, "/_server/inspector/page")

    assert response_status(sent) == 200
    assert response_headers(sent)[b"content-type"].startswith(b"text/html")
    assert b"worker-grid" in response_body(sent)


async def test_the_census_is_json(
    inspector_server, http_request, response_status, response_headers, response_body
):
    sent = await http_request(inspector_server, "/_server/inspector/census")

    assert response_status(sent) == 200
    assert response_headers(sent)[b"content-type"].startswith(b"application/json")
    assert json.loads(response_body(sent)) == {}


async def test_the_inspector_mints_no_cookie(inspector_server, http_request, response_headers):
    for path in ("/_server/inspector/page", "/_server/inspector/census"):
        headers = await http_request(inspector_server, path)

        assert b"sticky_cid" not in response_headers(headers).get(b"set-cookie", b"")


async def test_the_stream_opens_with_the_census(inspector_server, sse_request):
    connection = await sse_request(inspector_server, "/_server/inspector/stream")

    frames = await connection.wait_frames(2)
    await connection.close()

    assert b"retry: 2000" in frames[0]
    assert b"event: census" in frames[1]


async def test_the_page_carries_its_containers_and_its_endpoints(
    inspector_server, http_request, response_body
):
    page = response_body(await http_request(inspector_server, "/_server/inspector/page"))

    for container_id in ("commander-panel", "worker-grid", "event-log", "last-read", "toggle-stream"):
        assert f'id="{container_id}"'.encode() in page
    assert b'"/census"' in page
    assert b'"/stream"' in page
