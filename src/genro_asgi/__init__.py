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

"""Minimal ASGI server core: the base server and the app-side contract."""

from .application import ApplicationGrammar, BaseApplication
from .applications import (
    McpApplication,
    McpOpenApiApplication,
    OpenApiApplication,
    ServerApplication,
)
from .applications.server_sections import AuthSection
from .asgi_server import AsgiServer
from .auth import (
    ApiKeyStore,
    AuthCore,
    AuthMethod,
    AuthMixin,
    FileApiKeyStore,
    FileUserStore,
    OidcMethod,
    PasswordMethod,
    UserStore,
)
from .channel import ChannelClient, Frame, FrameStream
from .communication import CommunicationMixin
from .config import (
    AsgiConfigBuilder,
    AsgiServerGrammar,
    ConfigError,
    ConfigurationHandler,
)
from .db import AsgiDbHandlerBase
from .exceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPForbidden,
    HTTPNotFound,
    HTTPUnauthorized,
    Redirect,
)
from .mcp import McpEngine, McpError
from .middleware import BaseMiddleware, MiddlewareMixin
from .plugin_mixin import PluginMixin
from .plugins import OpenAPIPlugin, OpenAPITranslator, router_openapi
from .registry import RegisteredRequest, RequestRegistry
from .request import Request
from .response import Response
from .routed_application import RoutedApplication
from .server import BaseServer
from .session import (
    Avatar,
    FileSessionStore,
    MemorySessionStore,
    Session,
    SessionMixin,
    SessionStore,
)
from .storage import LocalStorage, LocalStorageNode, StorageNode
from .storage_mixin import StorageMixin
from .tasks import TaskGrammar
from .types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "ASGIApp",
    "ApiKeyStore",
    "ApplicationGrammar",
    "AsgiConfigBuilder",
    "AsgiDbHandlerBase",
    "AsgiServer",
    "AsgiServerGrammar",
    "AuthCore",
    "AuthMethod",
    "AuthMixin",
    "AuthSection",
    "Avatar",
    "BaseApplication",
    "BaseMiddleware",
    "BaseServer",
    "ChannelClient",
    "CommunicationMixin",
    "ConfigError",
    "ConfigurationHandler",
    "FileApiKeyStore",
    "FileSessionStore",
    "FileUserStore",
    "Frame",
    "FrameStream",
    "HTTPBadRequest",
    "HTTPException",
    "HTTPForbidden",
    "HTTPNotFound",
    "HTTPUnauthorized",
    "LocalStorage",
    "LocalStorageNode",
    "McpApplication",
    "McpEngine",
    "McpError",
    "McpOpenApiApplication",
    "Message",
    "MemorySessionStore",
    "MiddlewareMixin",
    "OidcMethod",
    "OpenAPIPlugin",
    "OpenAPITranslator",
    "OpenApiApplication",
    "PasswordMethod",
    "PluginMixin",
    "Receive",
    "Redirect",
    "RegisteredRequest",
    "Request",
    "RequestRegistry",
    "Response",
    "RoutedApplication",
    "Scope",
    "Send",
    "ServerApplication",
    "Session",
    "SessionMixin",
    "SessionStore",
    "StorageMixin",
    "StorageNode",
    "TaskGrammar",
    "UserStore",
    "__version__",
    "router_openapi",
]

__version__ = "0.21.0"
