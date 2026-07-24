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

"""Auth capability package: the credential core, the mixin, and the login surface.

``AuthCore`` (basic/bearer/jwt verification) and ``AuthMixin`` (the §5.5
identity precedence over sessions). ``AuthMiddleware`` — the chain entry point
armed by the mixin — lives in ``middleware/authentication.py``. The login
surface — the self-describing ``AuthMethod``/``PasswordMethod`` (core 1d) and
the ``safe_next_path`` open-redirect guard — is re-exported here too, so every
consumer imports auth symbols from the package, never from its modules.
"""

from __future__ import annotations

from .api_key_store import ApiKeyStore, FileApiKeyStore
from .auth_method import AuthMethod, PasswordMethod, safe_next_path
from .core import AuthCore
from .mixin import AuthMixin
from .oidc_method import OidcMethod
from .user_store import FileUserStore, UserStore

__all__ = [
    "ApiKeyStore",
    "AuthCore",
    "AuthMethod",
    "AuthMixin",
    "FileApiKeyStore",
    "FileUserStore",
    "OidcMethod",
    "PasswordMethod",
    "UserStore",
    "safe_next_path",
]
