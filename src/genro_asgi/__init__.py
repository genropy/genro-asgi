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

"""genro-asgi - Minimal ASGI framework with routing via genro-routes.

Main components:
    AsgiServer: ASGI entry point, loads config, mounts apps
    AsgiApplication: Base class for mountable applications
    Response: HTTP response with auto content-type detection
    HttpRequest: HTTP request wrapper with headers, query, body

Middleware:
    AuthMiddleware: O(1) authentication (bearer, basic, JWT)
    CORSMiddleware: Cross-Origin Resource Sharing headers
    ErrorMiddleware: Exception handling and error responses

Storage:
    LocalStorage: Filesystem storage with mount system
    ResourceLoader: Hierarchical resource loading with fallback

Usage:
    from genro_asgi import AsgiServer

    server = AsgiServer(server_dir=".")
    server.run()  # Starts uvicorn

See config.yaml for configuration options.
"""

__version__ = "0.1.0"

from .datastructures import (
    Address,
    Headers,
    QueryParams,
    State,
    URL,
    headers_from_scope,
    query_params_from_scope,
)
from .exceptions import (
    HTTPException,
    HTTPForbidden,
    HTTPNotFound,
    HTTPUnauthorized,
    Redirect,
    WebSocketDisconnect,
    WebSocketException,
)
from .lifespan import Lifespan, ServerLifespan
from .request import (
    BaseRequest,
    HttpRequest,
    MsgRequest,
    RequestRegistry,
    REQUEST_FACTORIES,
)
from .response import (
    Response,
    make_cookie,
)
from .types import ASGIApp, Message, Receive, Scope, Send
from .utils import AsgiServerEnabler, ServerBinder
from .executors import (
    BaseExecutor,
    ExecutorError,
    ExecutorOverloadError,
    ExecutorRegistry,
    LocalExecutor,
)
from .server import AsgiServer, ServerConfig, Dispatcher
from .context import AsgiContext
from .applications import AsgiApplication
from .routers import StaticRouter
from .storage import LocalStorage, LocalStorageNode, StorageNode
from .websocket import WebSocket, WebSocketState

# Backwards compatibility alias
Request = HttpRequest

__all__ = [
    # Request classes
    "BaseRequest",
    "HttpRequest",
    "MsgRequest",
    "Request",  # alias for HttpRequest
    "RequestRegistry",
    "REQUEST_FACTORIES",
    # Response classes
    "Response",
    "Lifespan",
    "ServerLifespan",
    # Helper functions
    "make_cookie",
    # Data structures
    "Address",
    "URL",
    "Headers",
    "QueryParams",
    "State",
    "headers_from_scope",
    "query_params_from_scope",
    # Exceptions
    "HTTPException",
    "HTTPForbidden",
    "HTTPNotFound",
    "HTTPUnauthorized",
    "Redirect",
    "WebSocketException",
    "WebSocketDisconnect",
    # ASGI types
    "ASGIApp",
    "Message",
    "Receive",
    "Scope",
    "Send",
    # Server integration
    "AsgiServer",
    "ServerConfig",
    "Dispatcher",
    # Context
    "AsgiContext",
    # Applications
    "AsgiApplication",
    "ServerBinder",
    "AsgiServerEnabler",
    # Executors
    "BaseExecutor",
    "LocalExecutor",
    "ExecutorRegistry",
    "ExecutorError",
    "ExecutorOverloadError",
    # WebSocket
    "WebSocket",
    "WebSocketState",
    # Routers
    "StaticRouter",
    # Storage
    "LocalStorage",
    "LocalStorageNode",
    "StorageNode",
]
