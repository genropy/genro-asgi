# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for ServerApplication."""

from unittest.mock import MagicMock

from genro_asgi.server.server_app import ServerApplication


class TestServerApplication:
    """Test ServerApplication functionality."""

    def test_init_stores_server_reference(self):
        """ServerApplication stores reference to parent server."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": {}}
        app = ServerApplication(mock_server)
        assert app._server is mock_server

    def test_init_creates_router(self):
        """ServerApplication creates main router."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": {}}
        app = ServerApplication(mock_server)
        assert app.main is not None
        assert app.main.name == "main"

    def test_config_property(self):
        """config property returns server config."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": "shop", "apps": {"shop": {}}}
        app = ServerApplication(mock_server)
        assert app.config is mock_server.config

    def test_main_app_configured(self):
        """Return configured main_app when set."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": "shop", "apps": {"shop": {}, "api": {}}}
        app = ServerApplication(mock_server)
        assert app.main_app == "shop"

    def test_main_app_single_app(self):
        """Return single app name when only one app and no main_app configured."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": {"shop": {}}}
        app = ServerApplication(mock_server)
        assert app.main_app == "shop"

    def test_main_app_multiple_apps_none(self):
        """Return None when multiple apps and no main_app configured."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": {"shop": {}, "api": {}}}
        app = ServerApplication(mock_server)
        assert app.main_app is None

    def test_main_app_no_apps(self):
        """Return None when no apps configured."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": {}}
        app = ServerApplication(mock_server)
        assert app.main_app is None

    def test_main_app_apps_none(self):
        """Return None when apps is None."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": None}
        app = ServerApplication(mock_server)
        assert app.main_app is None
