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

__version__ = "0.1.0"

from .applications import AsgiApplication, StaticSite
from .datastructures import (
    Address,
    Headers,
    QueryParams,
    State,
    URL,
    headers_from_scope,
    query_params_from_scope,
)
from .exceptions import HTTPException, WebSocketDisconnect, WebSocketException
from .lifespan import Lifespan, ServerLifespan
from .request import (
    BaseRequest,
    HttpRequest,
    MsgRequest,
    RequestRegistry,
    REQUEST_FACTORIES,
)
from .response import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
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
from .servers import AsgiServer, AsgiPublisher
from .static import StaticFiles
from .static_router import StaticRouter
from .websocket import WebSocket, WebSocketState

# Backwards compatibility alias
Request = HttpRequest

__all__ = [
    # Application classes
    "AsgiApplication",
    "StaticSite",
    # Request classes
    "BaseRequest",
    "HttpRequest",
    "MsgRequest",
    "Request",  # alias for HttpRequest
    "RequestRegistry",
    "REQUEST_FACTORIES",
    # Response classes
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "StreamingResponse",
    "FileResponse",
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
    "AsgiPublisher",
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
    # Static files
    "StaticFiles",
    "StaticRouter",
]
