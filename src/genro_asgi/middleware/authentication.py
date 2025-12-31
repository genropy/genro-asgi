# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Authentication middleware for ASGI applications.

Supports Bearer tokens, Basic auth, and JWT with O(1) lookup at request time.
Sets scope["auth"] with authentication result for downstream handlers.

Backends:
    bearer: Static token lookup. O(1) via dict.
    basic: Username/password. O(1) via base64-encoded key.
    jwt: Token verification via pyjwt. Falls back from bearer if not found.

Config:
    bearer: Dict of {name: {token: "...", tags: "..."}}
    basic: Dict of {username: {password: "...", tags: "..."}}
    jwt: Dict of {name: {secret: "...", algorithm: "...", tags: "..."}}

scope["auth"] format:
    {"tags": [...], "identity": "...", "backend": "bearer|basic|jwt:name"}
    None if no Authorization header present.

Raises:
    HTTPException(401): If credentials present but invalid/expired.

Example:
    Enable in config.yaml::

        middleware:
          auth:
            bearer:
              api_key:
                token: "sk_live_abc123"
                tags: "api,read"
            basic:
              admin:
                password: "secret"
                tags: "admin"
            jwt:
              internal:
                secret: "my-jwt-secret"
                algorithm: "HS256"
"""

from __future__ import annotations

import base64
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from . import BaseMiddleware, headers_dict
from ..exceptions import HTTPException
from ..utils import split_and_strip

try:
    import jwt
    HAS_JWT = True
except ImportError:
    jwt = None  # type: ignore[assignment]
    HAS_JWT = False

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send

__all__ = ["AuthMiddleware"]


class AuthMiddleware(BaseMiddleware):
    """Authentication middleware with O(1) credential lookup.

    Extracts Authorization header, validates credentials against configured
    backends, and sets scope["auth"] with result.

    Attributes:
        _auth_config: Dict mapping auth type to credentials dict.

    Class Attributes:
        middleware_name: "auth" - identifier for config.
        middleware_order: 400 - runs after CORS.
        middleware_default: False - disabled by default.
    """

    middleware_name = "auth"
    middleware_order = 400
    middleware_default = False

    __slots__ = ("_auth_config",)

    def __init__(self, app: ASGIApp, **entries: Any) -> None:
        """Initialize authentication middleware.

        Args:
            app: Next ASGI application in the middleware chain.
            **entries: Auth configuration by type (bearer, basic, jwt).

        Note:
            Configuration is processed by _configure_{type} methods.
            Unknown auth types are silently ignored.
        """
        super().__init__(app)
        self._auth_config: defaultdict[str, dict[str, Any]] = defaultdict(dict)

        for auth_type, credentials in entries.items():
            method = getattr(self, f"_configure_{auth_type}", self._configure_default)
            method(credentials=credentials)

    def _configure_bearer(self, *, credentials: dict[str, Any]) -> None:
        """Configure bearer token authentication.

        Args:
            credentials: Dict of {name: {token: "...", tags: "..."}}.

        Raises:
            ValueError: If a token entry is missing 'token' value.

        Note:
            Tokens are stored in _auth_config["bearer"][token_value] for O(1) lookup.
        """
        for cred_name, config in credentials.items():
            token_value = config.get("token")
            if not token_value:
                raise ValueError(f"Bearer token '{cred_name}' missing 'token' value")
            self._auth_config["bearer"][token_value] = {
                "tags": split_and_strip(config.get("tags", [])),
                "identity": cred_name,
            }

    def _configure_basic(self, *, credentials: dict[str, Any]) -> None:
        """Configure HTTP Basic authentication.

        Args:
            credentials: Dict of {username: {password: "...", tags: "..."}}.

        Raises:
            ValueError: If a user entry is missing 'password' value.

        Note:
            Credentials are stored as base64(username:password) for O(1) lookup.
        """
        for username, config in credentials.items():
            password = config.get("password")
            if not password:
                raise ValueError(f"Basic auth user '{username}' missing 'password'")
            b64_key = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._auth_config["basic"][b64_key] = {
                "tags": split_and_strip(config.get("tags", [])),
                "identity": username,
            }

    def _configure_jwt(self, *, credentials: dict[str, Any]) -> None:
        """Configure JWT token verification.

        Args:
            credentials: Dict of {name: {secret: "...", algorithm: "...", tags: "..."}}.

        Raises:
            ImportError: If pyjwt is not installed.

        Note:
            Supports both symmetric (secret) and asymmetric (public_key) verification.
            Default algorithm is HS256.
        """
        if not HAS_JWT:
            raise ImportError("JWT config requires pyjwt. Install: pip install pyjwt")
        for config_name, config in credentials.items():
            self._auth_config["jwt"][config_name] = {
                "secret": config.get("secret"),
                "public_key": config.get("public_key"),
                "algorithm": config.get("algorithm", "HS256"),
                "default_tags": split_and_strip(config.get("tags", [])),
                "default_exp": config.get("exp", 3600),
            }

    def _configure_default(self, *, credentials: dict[str, Any]) -> None:
        """Fallback for unknown auth types.

        Args:
            credentials: Configuration dict (ignored).

        Note:
            Unknown auth types are silently ignored to allow forward compatibility.
        """
        pass

    def _get_auth(self, scope: Scope) -> tuple[str | None, str | None]:
        """Extract auth type and credentials from Authorization header.

        Args:
            scope: ASGI scope with _headers dict.

        Returns:
            Tuple of (auth_type, credentials) or (None, None) if no header.

        Note:
            Expects header format: "Type credentials" (e.g., "Bearer token123").
        """
        auth_header = scope["_headers"].get("authorization")
        if auth_header and " " in auth_header:
            auth_type, credentials = auth_header.split(" ", 1)
            return auth_type.lower(), credentials
        return None, None

    def _verify_jwt(self, credentials: str, jwt_config: dict[str, Any]) -> dict[str, Any] | None:
        """Verify JWT token and extract identity/tags from payload.

        Args:
            credentials: JWT token string.
            jwt_config: Config dict with secret/public_key and algorithm.

        Returns:
            Dict with identity and tags if valid, None if invalid/expired.

        Note:
            Uses 'sub' claim for identity, 'tags' claim for tags.
        """
        if not HAS_JWT or jwt is None:
            return None
        secret: str | bytes | None = jwt_config.get("secret") or jwt_config.get("public_key")
        if not secret:
            return None
        algorithm: str = jwt_config.get("algorithm", "HS256")
        try:
            payload = jwt.decode(credentials, secret, algorithms=[algorithm])
            return {
                "identity": payload.get("sub"),
                "tags": payload.get("tags", []),
            }
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def _authenticate(self, scope: Scope) -> dict[str, Any] | None:
        """Authenticate request using configured backends.

        Args:
            scope: ASGI scope with _headers dict.

        Returns:
            Auth dict with tags/identity/backend if valid, None if no header.

        Raises:
            HTTPException: 401 if credentials present but invalid.

        Note:
            Uses dynamic dispatch to _auth_{type} methods.
        """
        auth_type, credentials = self._get_auth(scope)
        if not auth_type or not credentials:
            return None
        method = getattr(self, f"_auth_{auth_type}", self._auth_default)
        result = method(auth_type=auth_type, credentials=credentials)
        if result is None:
            raise HTTPException(
                401,
                detail="Invalid or expired credentials",
                headers={"WWW-Authenticate": f"{auth_type.title()} realm=\"api\""},
            )
        return result

    def _auth_bearer(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
        """Authenticate bearer token.

        Args:
            credentials: Token string from Authorization header.
            **kw: Additional args (unused).

        Returns:
            Auth dict if valid, None if not found (falls back to JWT).

        Note:
            If token not found in static config, attempts JWT verification.
        """
        entry = self._auth_config.get("bearer", {}).get(credentials)
        if entry:
            return {"tags": entry["tags"], "identity": entry["identity"], "backend": "bearer"}
        return self._auth_jwt(credentials=credentials)

    def _auth_basic(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
        """Authenticate HTTP Basic credentials.

        Args:
            credentials: Base64-encoded "username:password" from header.
            **kw: Additional args (unused).

        Returns:
            Auth dict if valid, None if credentials not found.
        """
        entry = self._auth_config.get("basic", {}).get(credentials)
        if entry:
            return {"tags": entry["tags"], "identity": entry["identity"], "backend": "basic"}
        return None

    def _auth_jwt(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
        """Authenticate JWT token by trying all configured verifiers.

        Args:
            credentials: JWT token string.
            **kw: Additional args (unused).

        Returns:
            Auth dict if valid with any verifier, None otherwise.

        Note:
            Tries each configured JWT verifier in order until one succeeds.
        """
        for name, jwt_config in self._auth_config.get("jwt", {}).items():
            result = self._verify_jwt(credentials, jwt_config)
            if result:
                result["backend"] = f"jwt:{name}"
                return result
        return None

    def _auth_default(self, *, auth_type: str, **kw: Any) -> dict[str, Any] | None:
        """Fallback for unknown authentication types.

        Args:
            auth_type: The unrecognized auth type from header.
            **kw: Additional args (unused).

        Returns:
            Always None - unknown types are rejected.
        """
        return None

    def verify_credentials(self, username: str, password: str) -> dict[str, Any] | None:
        """Verify username/password against basic auth config.

        Useful for login endpoints that need to verify credentials
        before issuing a JWT token.

        Args:
            username: The username to verify.
            password: The password to verify.

        Returns:
            Dict with tags and identity if valid, None otherwise.
        """
        b64_key = base64.b64encode(f"{username}:{password}".encode()).decode()
        entry = self._auth_config.get("basic", {}).get(b64_key)
        if entry:
            return {"tags": entry["tags"], "identity": username}
        return None

    @headers_dict
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request with authentication.

        For HTTP requests, extracts and validates Authorization header,
        setting scope["auth"] with the result.

        Args:
            scope: ASGI scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Note:
            Uses @headers_dict decorator to populate scope["_headers"].
            Non-HTTP requests pass through without auth processing.
        """
        if scope["type"] == "http":
            scope["auth"] = self._authenticate(scope)
        await self.app(scope, receive, send)


if __name__ == "__main__":
    pass
