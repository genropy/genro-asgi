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

"""The two-stage demux: what the front claims and what reaches the site.

The invariants pinned here are the legacy ones. Stage 1 reads the first path
segment against ``internal_roots``; stage 2 resolves the FULL path structurally.
A structural miss under a claimed root belongs to the site; an existing node
does not — not even when a filter would deny it, which is what keeps a
protected native route from leaking the site behind it.

The forwarding half is stubbed here: ``RecordingSpa`` records what would
have been forwarded and answers a marker, so this file pins the demux decision
alone — the real forward is pinned in test_spa_application_forward.py.
"""

from __future__ import annotations

from typing import Any

from genro_routes import RoutingClass, route

from genro_asgi import AsgiServer, Avatar, BaseMiddleware
from genro_asgi.applications import SpaApplication
from genro_asgi.response import Response
from genro_asgi.types import Receive, Scope, Send


class Orders(RoutingClass):
    """A mounted sub-tree: ``orders`` is a claimed root with one entry."""

    @route()
    def list(self) -> dict[str, bool]:
        return {"orders": True}

    @route()
    def collect(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # the extra path segments reach the handler as the bound ``args`` kwarg
        return {"collected": list(kwargs.get("args", args))}


class RecordingSpa(SpaApplication):
    """A front that records forwards instead of performing them."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.forwarded: list[str] = []
        self.add_branches({"name": "orders", "instance": Orders()})

    @route()
    def ping(self) -> dict[str, bool]:
        return {"ping": True}

    @route(auth_rule="admin")
    def secret(self) -> dict[str, bool]:
        return {"secret": True}

    async def forward_request(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.forwarded.append(str(scope.get("path", "/")))
        await Response("forwarded", media_type="text/plain")(scope, receive, send)


class StampAuthMiddleware(BaseMiddleware):
    """Stamps a fixed identity on ``scope["auth"]`` after the real auth pass."""

    middleware_order = 500

    def __init__(self, app: Any, server: Any, *, avatar: Avatar | None = None, **options: Any):
        self._avatar = avatar
        super().__init__(app, server, **options)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        scope["auth"] = self._avatar
        await self.app(scope, receive, send)


def spa_server(app: SpaApplication, avatar: Avatar | None = None) -> AsgiServer:
    """A server whose chain stamps ``avatar`` as the request identity."""
    return AsgiServer(
        applications=[app],
        middleware={"stamp": {"avatar": avatar}},
        middleware_registry={"stamp": StampAuthMiddleware},
    )


def make_spa() -> RecordingSpa:
    return RecordingSpa(mount="", workers=0)


# ----------------------------------------------------------------------
# internal_roots
# ----------------------------------------------------------------------


def test_internal_roots_collect_entries_and_routers() -> None:
    spa = make_spa()
    assert {"ping", "secret", "orders"} <= spa.internal_roots


def test_index_is_never_a_claimed_root() -> None:
    spa = make_spa()
    assert "index" not in spa.internal_roots


def test_internal_roots_are_recomputed_per_access() -> None:
    spa = make_spa()
    assert "cart" not in spa.internal_roots
    spa.add_branches({"name": "cart", "instance": Orders()})
    assert "cart" in spa.internal_roots


# ----------------------------------------------------------------------
# resolves_natively — the structural half
# ----------------------------------------------------------------------


def test_resolves_natively_true_for_an_existing_node() -> None:
    spa = make_spa()
    assert spa.resolves_natively("ping") is True
    assert spa.resolves_natively("orders/list") is True


def test_resolves_natively_false_for_a_structural_miss() -> None:
    spa = make_spa()
    assert spa.resolves_natively("orders/detail") is False
    assert spa.resolves_natively("cart/view") is False


def test_resolves_natively_true_for_a_variadic_handler() -> None:
    spa = make_spa()
    assert spa.resolves_natively("orders/collect/x/y") is True


def test_resolves_natively_true_for_an_existing_but_denied_node() -> None:
    spa = make_spa()
    assert spa.resolves_natively("secret") is True


# ----------------------------------------------------------------------
# The demux matrix, driven end to end
# ----------------------------------------------------------------------


class TestDemux:
    async def test_a_native_route_answers_locally(
        self, http_request, response_status, response_body
    ) -> None:
        spa = make_spa()
        sent = await http_request(spa_server(spa), "/ping")
        assert response_status(sent) == 200
        assert response_body(sent) == b'{"ping":true}'
        assert spa.forwarded == []

    async def test_a_non_root_first_segment_forwards(self, http_request, response_status) -> None:
        spa = make_spa()
        sent = await http_request(spa_server(spa), "/catalog/item/3")
        assert spa.forwarded == ["/catalog/item/3"]
        assert response_status(sent) == 200

    async def test_the_bare_root_path_belongs_to_the_site(
        self, http_request, response_status
    ) -> None:
        # "/" has no first segment, and "index" is no claimed root: the
        # inherited splash never answers the site's entry page away
        spa = make_spa()
        sent = await http_request(spa_server(spa), "/")
        assert spa.forwarded == ["/"]
        assert response_status(sent) == 200

    async def test_a_structural_miss_under_a_claimed_root_falls_through(
        self, http_request
    ) -> None:
        spa = make_spa()
        await http_request(spa_server(spa), "/orders/detail")
        assert spa.forwarded == ["/orders/detail"]

    async def test_a_variadic_handler_under_a_claimed_root_never_falls_through(
        self, http_request, response_status, response_body
    ) -> None:
        spa = make_spa()
        sent = await http_request(spa_server(spa), "/orders/collect/x/y")
        assert spa.forwarded == []
        assert response_status(sent) == 200
        assert response_body(sent) == b'{"collected":["x","y"]}'

    async def test_an_existing_but_denied_route_answers_401_natively(
        self, http_request, response_status
    ) -> None:
        spa = make_spa()
        sent = await http_request(spa_server(spa, avatar=None), "/secret")
        assert response_status(sent) == 401
        assert spa.forwarded == []

    async def test_the_denied_route_answers_natively_for_a_wrong_tag_too(
        self, http_request, response_status
    ) -> None:
        spa = make_spa()
        sent = await http_request(spa_server(spa, Avatar("u", tags=["guest"])), "/secret")
        assert response_status(sent) == 403
        assert spa.forwarded == []
