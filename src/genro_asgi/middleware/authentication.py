# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Authentication middleware with O(1) lookup.

YAML Configuration:
    middleware: cors, auth

    auth_middleware:
      api_tokens:
        type: bearer
        reader_token:
          token: "tk_abc123"
          tags: "read"
        writer_token:
          token: "tk_xyz789"
          tags: "read,write"

      staff:
        type: basic
        mrossi:
          password: "secret123"
          tags: "read,write"
        admin:
          password: "supersecret"
          tags: "admin"

      jwt_internal:
        type: jwt
        secret: "my-secret"
        algorithm: "HS256"

scope["auth"] format (if authenticated):
    Bearer: {"tags": ["read"], "token_name": "reader_token", "entry": "api_tokens", "backend": "bearer"}
    Basic:  {"tags": ["read"], "username": "mrossi", "entry": "staff", "backend": "basic"}

scope["auth"] = None if no entry matches.
"""

from __future__ import annotations

import base64
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from . import BaseMiddleware, headers_dict
from ..exceptions import HTTPException
from ..utils import normalize_list

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

        for entry_name, config in entries.items():
            auth_type = config.pop("type", "")
            method = getattr(self, f"_configure_{auth_type}", self._configure_default)
            method(entry_name=entry_name, config=config)

    def _configure_bearer(self, *, entry_name: str, config: Any, **kw: Any) -> None:
        """Configure bearer tokens. All keys are token names."""
        for token_name, token_config in config.items():
            token_value = token_config.get("token")
            if not token_value:
                raise ValueError(f"Bearer token '{token_name}' missing 'token' value")
            self._auth_config["bearer"][token_value] = {
                "tags": normalize_list(token_config.get("tags", [])),
                "token_name": token_name,
                "entry": entry_name,
            }

    def _configure_basic(self, *, entry_name: str, config: Any, **kw: Any) -> None:
        """Configure basic auth. All keys are usernames."""
        for username, user_config in config.items():
            password = user_config.get("password")
            if not password:
                raise ValueError(f"Basic auth user '{username}' missing 'password'")
            b64_key = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._auth_config["basic"][b64_key] = {
                "tags": normalize_list(user_config.get("tags", [])),
                "username": username,
                "entry": entry_name,
            }

    def _configure_jwt(self, *, entry_name: str, config: Any, **kw: Any) -> None:
        """Configure JWT verifier."""
        self._auth_config["jwt"][entry_name] = {
            "secret": config.get("secret"),
            "public_key": config.get("public_key"),
            "algorithm": config.get("algorithm", "HS256"),
        }

    def _configure_default(self, *, entry_name: str, **kw: Any) -> None:
        """Fallback for unknown auth types."""
        pass

    def _get_auth(self, scope: Scope) -> tuple[str | None, str | None]:
        """Extract auth type and credentials from Authorization header."""
        auth_header = scope["_headers"].get("authorization")
        if auth_header and " " in auth_header:
            auth_type, credentials = auth_header.split(" ", 1)
            return auth_type.lower(), credentials
        return None, None

    def _verify_jwt(self, credentials: str, jwt_config: dict[str, Any]) -> dict[str, Any] | None:
        """Verify JWT token. Stub for future implementation."""
        # TODO: implement with pyjwt
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
            return {**entry, "backend": "bearer"}
        return self._auth_jwt(credentials=credentials)

    def _auth_basic(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
        """Authenticate basic auth credentials."""
        entry = self._auth_config.get("basic", {}).get(credentials)
        if entry:
            return {**entry, "backend": "basic"}
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

    @headers_dict
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope["auth"] = self._authenticate(scope)
        await self.app(scope, receive, send)


if __name__ == "__main__":
    pass
