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

"""Contract tests for the cooperative base classes (SPECIFICATION.md §4, D16).

The cooperative chain: base + two mixin-style layers + concrete class, each
layer peeling its own kwargs; leftovers raise ``TypeError`` naming them.
The ownership channel: ``server`` assigned exactly once at attach/mount.
The base answers: ``authenticate``/``session`` return ``None``.
"""

import asyncio

import pytest

from genro_asgi import BaseApplication, BaseServer


class AlphaMixin:
    """Mixin layer: peels ``alpha`` and forwards the rest."""

    def __init__(self, **kwargs):
        self.alpha = kwargs.pop("alpha")
        super().__init__(**kwargs)


class BetaMixin:
    """Mixin layer: peels ``beta`` and forwards the rest."""

    def __init__(self, **kwargs):
        self.beta = kwargs.pop("beta")
        super().__init__(**kwargs)


class ConcreteApp(AlphaMixin, BetaMixin, BaseApplication):
    """Cooperative chain: base + two mixin-style layers + concrete class."""


class TestCooperativeChain:
    def test_each_layer_receives_its_kwargs(self):
        app = ConcreteApp(alpha=1, beta=2, mount_name="demo")
        assert app.alpha == 1
        assert app.beta == 2
        assert app.mount_name == "demo"

    def test_leftover_kwarg_raises_naming_it(self):
        with pytest.raises(TypeError, match="bogus"):
            ConcreteApp(alpha=1, beta=2, bogus=3)

    def test_server_leftover_kwarg_raises_naming_it(self):
        with pytest.raises(TypeError, match="bogus"):
            BaseServer(primary=BaseApplication(), bogus=3)


class TestOwnershipChannel:
    def test_server_is_none_until_attached(self):
        assert BaseApplication().server is None

    def test_primary_attach_assigns_server(self):
        primary = BaseApplication()
        server = BaseServer(primary=primary)
        assert primary.server is server

    def test_mount_assigns_server_and_registers_by_mount_name(self):
        server = BaseServer(primary=BaseApplication())
        api = BaseApplication(mount_name="api")
        server.mount(api)
        assert api.server is server
        assert server.mounts["api"] is api

    def test_second_assignment_raises(self):
        primary = BaseApplication()
        BaseServer(primary=primary)
        with pytest.raises(RuntimeError):
            BaseServer(primary=primary)

    def test_mounting_on_a_second_server_raises(self):
        api = BaseApplication(mount_name="api")
        BaseServer(primary=BaseApplication()).mount(api)
        with pytest.raises(RuntimeError):
            BaseServer(primary=BaseApplication()).mount(api)


class TestServerContract:
    def test_missing_primary_raises(self):
        with pytest.raises(TypeError, match="primary"):
            BaseServer()

    def test_duplicate_mount_name_raises(self):
        server = BaseServer(primary=BaseApplication())
        server.mount(BaseApplication(mount_name="api"))
        with pytest.raises(ValueError, match="api"):
            server.mount(BaseApplication(mount_name="api"))

    def test_mount_without_mount_name_raises(self):
        server = BaseServer(primary=BaseApplication())
        with pytest.raises(ValueError, match="mount_name"):
            server.mount(BaseApplication())

    def test_authenticate_answers_nobody(self):
        server = BaseServer(primary=BaseApplication())
        assert server.authenticate(None) is None

    def test_session_answers_none(self):
        server = BaseServer(primary=BaseApplication())
        assert server.session(None) is None


class TestAppContract:
    def test_lifecycle_hooks_exist_and_default_to_noop(self):
        app = BaseApplication()
        assert app.on_startup() is None
        assert app.on_shutdown() is None

    def test_base_asgi_call_is_not_implemented(self):
        app = BaseApplication()
        with pytest.raises(NotImplementedError):
            asyncio.run(app({}, None, None))
