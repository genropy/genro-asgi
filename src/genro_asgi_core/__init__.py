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

from .application import BaseApplication
from .asgi_server import AsgiServer
from .auth import ApiKeyStore, AuthCore, AuthMixin, FileApiKeyStore, FileUserStore, UserStore
from .channel import ChannelClient, Frame, FrameStream
from .communication import CommunicationMixin
from .config import AsgiConfigBuilder, ConfigurationHandler, Projection
from .db import AsgiDbHandlerBase
from .exceptions import HTTPException, Redirect
from .middleware import BaseMiddleware, MiddlewareMixin
from .registry import RegisteredRequest, RequestRegistry
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
from .types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "ASGIApp",
    "ApiKeyStore",
    "AsgiConfigBuilder",
    "AsgiDbHandlerBase",
    "AsgiServer",
    "AuthCore",
    "AuthMixin",
    "Avatar",
    "BaseApplication",
    "BaseMiddleware",
    "BaseServer",
    "ChannelClient",
    "CommunicationMixin",
    "ConfigurationHandler",
    "FileApiKeyStore",
    "FileSessionStore",
    "FileUserStore",
    "Frame",
    "FrameStream",
    "HTTPException",
    "LocalStorage",
    "LocalStorageNode",
    "Message",
    "MemorySessionStore",
    "MiddlewareMixin",
    "Projection",
    "Receive",
    "Redirect",
    "RegisteredRequest",
    "RequestRegistry",
    "Scope",
    "Send",
    "Session",
    "SessionMixin",
    "SessionStore",
    "StorageMixin",
    "StorageNode",
    "UserStore",
    "__version__",
]

__version__ = "0.1.0"
