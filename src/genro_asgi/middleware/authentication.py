# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Authentication middleware with O(1) lookup.

YAML Configuration:
    middleware: cors, auth

    auth_middleware:
      bearer:
        reader_token:
          token: "tk_abc123"
          tags: "read"
        writer_token:
          token: "tk_xyz789"
          tags: "read,write"

      basic:
        mrossi:
          password: "secret123"
          tags: "read,write"
        admin:
          password: "supersecret"
          tags: "admin"

      jwt:
        internal:
          secret: "my-secret"
          algorithm: "HS256"
          tags: "read,write"
          exp: 3600

scope["auth"] format (if authenticated):
    Bearer: {"tags": ["read"], "identity": "reader_token", "backend": "bearer"}
    Basic:  {"tags": ["read"], "identity": "mrossi", "backend": "basic"}
    JWT:    {"tags": ["read"], "identity": "sub_from_token", "backend": "jwt:internal"}

scope["auth"] = None if no auth header present.
Raises HTTPException(401) if credentials are present but invalid.
"""

from __future__ import annotations

import base64
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from . import BaseMiddleware, headers_dict
from ..exceptions import HTTPException
from ..utils import normalize_list

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
    """Authentication middleware with O(1) lookup at request time."""

    middleware_name = "auth"
    middleware_order = 400
    middleware_default = False

    __slots__ = ("_auth_config",)

    def __init__(self, app: ASGIApp, **entries: Any) -> None:
        super().__init__(app)
        self._auth_config: defaultdict[str, dict[str, Any]] = defaultdict(dict)

        for auth_type, credentials in entries.items():
            method = getattr(self, f"_configure_{auth_type}", self._configure_default)
            method(credentials=credentials)

    def _configure_bearer(self, *, credentials: dict[str, Any]) -> None:
        """Configure bearer tokens. Each entry: {token: "...", tags: "..."}"""
        for cred_name, config in credentials.items():
            token_value = config.get("token")
            if not token_value:
                raise ValueError(f"Bearer token '{cred_name}' missing 'token' value")
            self._auth_config["bearer"][token_value] = {
                "tags": normalize_list(config.get("tags", [])),
                "identity": cred_name,
            }

    def _configure_basic(self, *, credentials: dict[str, Any]) -> None:
        """Configure basic auth. Each entry: {password: "...", tags: "..."}"""
        for username, config in credentials.items():
            password = config.get("password")
            if not password:
                raise ValueError(f"Basic auth user '{username}' missing 'password'")
            b64_key = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._auth_config["basic"][b64_key] = {
                "tags": normalize_list(config.get("tags", [])),
                "identity": username,
            }

    def _configure_jwt(self, *, credentials: dict[str, Any]) -> None:
        """Configure JWT verifiers. Each entry: {secret/public_key, algorithm, tags, exp}"""
        if not HAS_JWT:
            raise ImportError("JWT config requires pyjwt. Install: pip install pyjwt")
        for config_name, config in credentials.items():
            self._auth_config["jwt"][config_name] = {
                "secret": config.get("secret"),
                "public_key": config.get("public_key"),
                "algorithm": config.get("algorithm", "HS256"),
                "default_tags": normalize_list(config.get("tags", [])),
                "default_exp": config.get("exp", 3600),
            }

    def _configure_default(self, *, credentials: dict[str, Any]) -> None:
        """Fallback for unknown auth types - ignored."""
        pass

    def _get_auth(self, scope: Scope) -> tuple[str | None, str | None]:
        """Extract auth type and credentials from Authorization header."""
        auth_header = scope["_headers"].get("authorization")
        if auth_header and " " in auth_header:
            auth_type, credentials = auth_header.split(" ", 1)
            return auth_type.lower(), credentials
        return None, None

    def _verify_jwt(self, credentials: str, jwt_config: dict[str, Any]) -> dict[str, Any] | None:
        """Verify JWT token and extract payload."""
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
        """Authenticate request via dynamic dispatch.

        Returns auth dict if valid, None if no auth header.
        Raises HTTPException(401) if credentials are present but invalid.
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
        """Authenticate bearer token. Falls back to JWT if not found."""
        entry = self._auth_config.get("bearer", {}).get(credentials)
        if entry:
            return {"tags": entry["tags"], "identity": entry["identity"], "backend": "bearer"}
        return self._auth_jwt(credentials=credentials)

    def _auth_basic(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
        """Authenticate basic auth credentials."""
        entry = self._auth_config.get("basic", {}).get(credentials)
        if entry:
            return {"tags": entry["tags"], "identity": entry["identity"], "backend": "basic"}
        return None

    def _auth_jwt(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
        """Authenticate JWT token by trying all configured verifiers."""
        for name, jwt_config in self._auth_config.get("jwt", {}).items():
            result = self._verify_jwt(credentials, jwt_config)
            if result:
                result["backend"] = f"jwt:{name}"
                return result
        return None

    def _auth_default(self, *, auth_type: str, **kw: Any) -> dict[str, Any] | None:
        """Fallback for unknown auth types."""
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
        if scope["type"] == "http":
            scope["auth"] = self._authenticate(scope)
        await self.app(scope, receive, send)


if __name__ == "__main__":
    pass
