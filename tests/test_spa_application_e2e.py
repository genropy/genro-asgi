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

"""The whole front in the single role: nothing stubbed between server and site.

``SpaApplication(workers=0, local_worker=True)`` holds its worker in this very
process, on a ``LocalChannel``, so a request entering the ASGI server crosses
the real demux, the real cookie, the real CALL/REPLY envelope and the real WSGI
seam before coming back — the same machinery a spawned child would run
(design §3.5a). The consumer seam is a worker subclass hosting a WSGI site,
which is exactly how issue #3 says the legacy site arrives.

What the earlier phases pinned in isolation is pinned here together: the two
demux outcomes (native, gated, structural miss), the ``sticky_cid`` cookie
minted on the first anonymous request, and the identity the forward routes on
before and after a login has been folded.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

import pytest
from genro_routes import route

from genro_asgi.applications import SpaApplication
from genro_asgi.applications.spa_app import STICKY_CID_COOKIE
from genro_asgi.channel.frame import Frame
from genro_asgi.spa.worker import UserStickyWorker
from genro_asgi.types import Message

from .test_spa_application_demux import Orders, spa_server


class SiteWorker(UserStickyWorker):
    """The consumer's worker: it hosts a WSGI site and records what it served.

    ``wsgi_app`` is the seam Phase 3 opened — assigned here by the subclass, as
    a consumer would. The recording rides ``serve_http``, which receives the
    identity the forward routed on and carries it into the environ.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.served: list[dict[str, Any]] = []
        self.wsgi_app = self.site

    def site(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        start_response("200 OK", [("content-type", "text/plain")])
        return [f"site:{environ['PATH_INFO']}".encode()]

    async def serve_http(
        self, frame: Frame, http: dict[str, Any], identity: str | None = None
    ) -> None:
        self.served.append({"identity": identity, "http": http})
        await super().serve_http(frame, http, identity)


class SiteSpa(SpaApplication):
    """The front a consumer mounts: its own routes, everything else the site's."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_branches({"name": "orders", "instance": Orders()})

    @route()
    def ping(self) -> dict[str, bool]:
        return {"ping": True}

    @route(auth_rule="admin")
    def secret(self) -> dict[str, bool]:
        return {"secret": True}


@pytest.fixture
async def site() -> Any:
    """A front in the single role, its pool started and its site hosted."""
    spa = SiteSpa(
        mount="",
        workers=0,
        local_worker=True,
        worker_class=f"{__name__}:SiteWorker",
    )
    # One server for the whole test: an application is owned by one and only one.
    spa_server(spa)
    await spa.on_startup()
    try:
        yield spa
    finally:
        await spa.on_shutdown()


def cookie_header(cid: str) -> list[tuple[bytes, bytes]]:
    return [(b"cookie", f"{STICKY_CID_COOKIE}={cid}".encode())]


def sticky_cookies(sent: list[Message]) -> list[str]:
    """Every ``sticky_cid`` Set-Cookie of a response.

    Read off the raw header pairs, never off a dict: the server's own session
    middleware issues a Set-Cookie of its own on the same response.
    """
    start = next(message for message in sent if message["type"] == "http.response.start")
    return [
        value.decode("latin-1")
        for name, value in start["headers"]
        if name == b"set-cookie" and value.startswith(f"{STICKY_CID_COOKIE}=".encode())
    ]


def minted_cid(sent: list[Message]) -> str:
    """The cid the front just issued, read off its own Set-Cookie."""
    return sticky_cookies(sent)[0].split(";")[0].split("=", 1)[1]


# ----------------------------------------------------------------------
# The site behind the front
# ----------------------------------------------------------------------


async def test_a_site_path_is_served_by_the_worker_and_gets_a_cookie(
    site: SiteSpa, http_request, response_status, response_body
) -> None:
    sent = await http_request(site.server, "/catalog/item/3")
    assert response_status(sent) == 200
    assert response_body(sent) == b"site:/catalog/item/3"
    cid = minted_cid(sent)
    assert len(cid) == 32
    # The whole round trip happened on the worker, and it saw the front's cid.
    served = site.commander.worker.served
    assert [entry["identity"] for entry in served] == [cid]
    assert served[0]["http"]["path"] == "/catalog/item/3"


async def test_a_structural_miss_under_a_claimed_root_reaches_the_site(
    site: SiteSpa, http_request, response_body
) -> None:
    sent = await http_request(site.server, "/orders/detail")
    assert response_body(sent) == b"site:/orders/detail"


# ----------------------------------------------------------------------
# The front's own routes
# ----------------------------------------------------------------------


async def test_a_native_route_answers_locally(
    site: SiteSpa, http_request, response_status, response_body
) -> None:
    sent = await http_request(site.server, "/ping")
    assert response_status(sent) == 200
    assert response_body(sent) == b'{"ping":true}'
    assert site.commander.worker.served == []


async def test_a_gated_native_route_answers_401_natively(
    site: SiteSpa, http_request, response_status
) -> None:
    sent = await http_request(site.server, "/secret")
    assert response_status(sent) == 401
    assert site.commander.worker.served == []


# ----------------------------------------------------------------------
# The identity, before and after the login fold
# ----------------------------------------------------------------------


async def test_the_forward_routes_on_the_real_user_once_the_login_is_folded(
    site: SiteSpa, http_request
) -> None:
    sent = await http_request(site.server, "/catalog")
    cid = minted_cid(sent)

    # The connection and its login are the site's own business, taken through
    # the channel ops exactly as a hosted page would take them.
    await site.commander.forward_call(cid, "/op/new_connection")
    await site.commander.forward_call(cid, "/op/change_connection_user", {"user": "alice"})
    assert site.commander.connection_user[cid] == "alice"

    await http_request(site.server, "/catalog", headers=cookie_header(cid))

    # Anonymous first, the real user after: the front reads the fold's own
    # surface and keeps no state of its own.
    assert [entry["identity"] for entry in site.commander.worker.served] == [cid, "alice"]


async def test_a_carried_cid_is_not_re_issued(
    site: SiteSpa, http_request
) -> None:
    sent = await http_request(site.server, "/catalog")
    cid = minted_cid(sent)
    again = await http_request(site.server, "/catalog", headers=cookie_header(cid))
    assert sticky_cookies(again) == []
