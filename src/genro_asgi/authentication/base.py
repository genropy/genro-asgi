# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Authentication backends for AuthMiddleware.

Provides pluggable backends matching Authorization header schemes:
- BearerBackend: "Authorization: Bearer <token>"
- BasicBackend: "Authorization: Basic <base64(user:pass)>"

YAML Configuration (under auth_middleware):
    auth_middleware:
      tokens:
        type: bearer
        tokens:
          reader_token:
            token: "tk_abc123"
            tags: "read"
          writer_token:
            token: "tk_xyz789"
            tags: "read,write"

      users:
        type: basic
        users:
          mrossi:
            password: "secret123"
            tags: "read,write"
          admin:
            password: "supersecret"
            tags: "admin"

      # Future - database users:
      db_users:
        type: basic
        usertable: users
        username_column: username
        password_column: password_hash
        tags_column: roles

Auth dict format (stored in scope["auth"]):
    {
        "tags": ["read", "write"],
        "identity": "mrossi",         # username or token name
        "backend": "basic"            # which backend matched
    }
"""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from typing import Any

from ..utils import split_and_strip

__all__ = ["AuthBackend", "BearerBackend", "BasicBackend"]


class AuthBackend(ABC):
    """Base class for authentication backends.

    Each backend handles a specific Authorization header type.
    Subclasses must set auth_type and implement try_auth().
    """

    auth_type: str = ""  # lowercase: "bearer", "basic"

    @abstractmethod
    def try_auth(self, credentials: str, config: dict[str, Any]) -> dict[str, Any] | None:
        """Try to authenticate using credentials.

        Args:
            credentials: Value after scheme prefix (token or base64).
            config: Entry config dict (has type, tokens/users, etc.)

        Returns:
            Auth dict {"tags": [...], "identity": ..., "backend": ...} or None.
        """
        ...


class BearerBackend(AuthBackend):
    """Bearer token authentication.

    Handles: Authorization: Bearer <token>
    Looks up token in config["tokens"] dict.

    Config format:
        tokens:
          type: bearer
          tokens:
            reader_token:
              token: "tk_abc123"
              tags: "read"
            writer_token:
              token: "tk_xyz789"
              tags: "read,write"
    """

    auth_type = "bearer"

    def try_auth(self, credentials: str, config: dict[str, Any]) -> dict[str, Any] | None:
        """Check if bearer token matches any configured token.

        Args:
            credentials: The bearer token from header.
            config: Must have "tokens" dict.

        Returns:
            Auth dict if token matches, None otherwise.
        """
        tokens = config.get("tokens", {})
        if hasattr(tokens, "as_dict"):
            tokens = tokens.as_dict()

        for token_name, token_config in tokens.items():
            if hasattr(token_config, "as_dict"):
                token_config = token_config.as_dict()

            expected = token_config.get("token")
            if expected and credentials == expected:
                return {
                    "tags": split_and_strip(token_config.get("tags", [])),
                    "identity": token_name,
                    "backend": self.auth_type,
                }
        return None


class BasicBackend(AuthBackend):
    """Basic authentication (username:password).

    Handles: Authorization: Basic <base64(username:password)>
    Looks up username in config["users"] dict.

    Config format (inline users):
        users:
          type: basic
          users:
            mrossi:
              password: "secret123"
              tags: "read,write"

    Future config format (database):
        db_users:
          type: basic
          usertable: users
          username_column: username
          password_column: password_hash
          tags_column: roles
    """

    auth_type = "basic"

    def try_auth(self, credentials: str, config: dict[str, Any]) -> dict[str, Any] | None:
        """Check if basic credentials match configured user.

        Args:
            credentials: Base64-encoded "username:password".
            config: Must have "users" dict or "usertable" (future).

        Returns:
            Auth dict if credentials match, None otherwise.
        """
        # Decode base64 credentials
        try:
            decoded = base64.b64decode(credentials).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None

        if ":" not in decoded:
            return None

        username, password = decoded.split(":", 1)

        # Future: check usertable for database lookup
        if "usertable" in config:
            # TODO: implement database lookup
            return None

        # Inline users lookup
        users = config.get("users", {})
        if hasattr(users, "as_dict"):
            users = users.as_dict()

        user_config = users.get(username)
        if user_config is None:
            return None

        if hasattr(user_config, "as_dict"):
            user_config = user_config.as_dict()

        expected_pass = user_config.get("password")
        if expected_pass and password == expected_pass:
            return {
                "tags": split_and_strip(user_config.get("tags", [])),
                "identity": username,
                "backend": self.auth_type,
            }
        return None


if __name__ == "__main__":
    pass
