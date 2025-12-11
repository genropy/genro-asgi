# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
WSX protocol utilities.

WSX (WebSocket eXtended) is a protocol that brings HTTP-like semantics
to WebSocket and NATS messaging.

This package provides only protocol-level utilities:
- Message parsing and building
- Format detection

Request handling is done by MsgRequest in request.py.
"""

from .protocol import (
    WSX_PREFIX,
    build_wsx_message,
    build_wsx_response,
    is_wsx_message,
    parse_wsx_message,
)

__all__ = [
    "WSX_PREFIX",
    "is_wsx_message",
    "parse_wsx_message",
    "build_wsx_message",
    "build_wsx_response",
]
