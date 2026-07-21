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

"""Auth core: credential configuration and header verification (salvage Q5).

``AuthCore`` holds the whole credential configuration and the verification
logic for the ``basic``, ``bearer`` and ``jwt`` schemes. It is router-free —
configured per instance from ``{'basic': ..., 'bearer': ..., 'jwt': [...]}``
and consumed by the server-side ``AuthMixin`` (never by walking wrappers).

Config sections (``_configure_<type>`` dynamic dispatch, unknown sections
ignored):
    basic:  ``{username: {password: "...", tags: "..."}}`` — O(1) lookup keyed
            by the base64 ``username:password`` the Basic header carries.
    bearer: ``{name: {token: "...", tags: "..."}}`` — O(1) lookup keyed by the
            token value.
    jwt:    ``[{secret|public_key, algorithm, tags, name}, ...]`` — a list of
            verifier configs, each tried in turn and decoded with pyjwt.

``authenticate(scope)`` reads the ``Authorization`` header via the shared
``headers_dict`` cache, dispatches ``_auth_<scheme>`` and returns an ``Avatar``
(the ONE identity type, unified with sessions) or ``None`` when NO credentials
are presented. Credentials PRESENT but invalid raise ``HTTPUnauthorized`` —
never a silent fallback; a malformed header (no scheme/value separator) is
present-but-invalid, so it raises too. Tag normalization (e.g. a JWT null
``tags`` claim) happens at the ``Avatar`` boundary, never ``list(None)``.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import jwt

from ..exceptions import HTTPUnauthorized
from ..middleware.base import headers_dict
from ..session.avatar import Avatar

if TYPE_CHECKING:
    from ..types import Scope

__all__ = ["AuthCore"]


def _split_and_strip(value: str | list[str] | None) -> list[str]:
    """Split a comma-separated string into a stripped list; pass a list through."""
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",")]
    return list(value)


def _basic_auth_key(username: str, password: str) -> str:
    """Base64-encode ``username:password`` as the HTTP Basic header carries it."""
    return base64.b64encode(f"{username}:{password}".encode()).decode()


class AuthCore:
    """Per-instance credential store and header verifier for basic/bearer/jwt."""

    def __init__(self, **entries: Any) -> None:
        """Build the credential store from the configured sections."""
        self._basic: dict[str, dict[str, Any]] = {}
        self._bearer: dict[str, dict[str, Any]] = {}
        self._jwt: list[dict[str, Any]] = []
        for auth_type, credentials in entries.items():
            configure = getattr(self, f"_configure_{auth_type}", self._configure_default)
            configure(credentials)

    def _configure_basic(self, credentials: dict[str, Any]) -> None:
        """Index Basic credentials by their base64 ``username:password`` key."""
        for username, config in credentials.items():
            password = config.get("password")
            if not password:
                raise ValueError(f"Basic auth user '{username}' missing 'password'")
            self._basic[_basic_auth_key(username, password)] = {
                "identity": username,
                "tags": _split_and_strip(config.get("tags")),
                "backend": "basic",
            }

    def _configure_bearer(self, credentials: dict[str, Any]) -> None:
        """Index Bearer credentials by their token value."""
        for name, config in credentials.items():
            token = config.get("token")
            if not token:
                raise ValueError(f"Bearer token '{name}' missing 'token' value")
            self._bearer[token] = {
                "identity": name,
                "tags": _split_and_strip(config.get("tags")),
                "backend": "bearer",
            }

    def _configure_jwt(self, credentials: list[dict[str, Any]]) -> None:
        """Store the JWT verifier configs as an ordered list of secrets/algorithms."""
        for config in credentials:
            self._jwt.append(
                {
                    "name": config.get("name"),
                    "secret": config.get("secret") or config.get("public_key"),
                    "algorithm": config.get("algorithm", "HS256"),
                    "tags": _split_and_strip(config.get("tags")),
                }
            )

    def _configure_default(self, credentials: Any) -> None:
        """Unknown config section — ignored (salvage semantics)."""

    def authenticate(self, scope: Scope) -> Avatar | None:
        """Verify the request's credentials; return an ``Avatar`` or ``None``.

        ``None`` when no ``Authorization`` header is presented; a present but
        invalid credential — including a malformed header with no scheme/value
        separator — raises ``HTTPUnauthorized`` (no silent fallback) carrying a
        ``WWW-Authenticate: Bearer`` challenge header.
        """
        header = headers_dict(scope).get("authorization")
        if not header:
            return None
        challenge = [(b"www-authenticate", b"Bearer")]
        if " " not in header:
            raise HTTPUnauthorized("Malformed Authorization header", headers=challenge)
        scheme, credentials = header.split(" ", 1)
        verify = getattr(self, f"_auth_{scheme.lower()}", self._auth_default)
        result = verify(credentials)
        if result is None:
            raise HTTPUnauthorized("Invalid or expired credentials", headers=challenge)
        return Avatar(result["identity"], result["tags"])

    def _auth_basic(self, credentials: str) -> dict[str, Any] | None:
        """Look up Basic credentials by their raw base64 header value."""
        return self._basic.get(credentials)

    def _auth_bearer(self, credentials: str) -> dict[str, Any] | None:
        """Resolve a Bearer token, falling back to the JWT verifiers."""
        entry = self._bearer.get(credentials)
        if entry is not None:
            return entry
        return self._auth_jwt(credentials)

    def _auth_jwt(self, credentials: str) -> dict[str, Any] | None:
        """Try each configured JWT verifier in turn."""
        for config in self._jwt:
            result = self._verify_jwt(credentials, config)
            if result is not None:
                return result
        return None

    def _auth_default(self, credentials: str) -> dict[str, Any] | None:
        """Unknown scheme — always rejected."""
        return None

    def _verify_jwt(self, credentials: str, config: dict[str, Any]) -> dict[str, Any] | None:
        """Decode a JWT with one verifier config; return the identity/tags or ``None``."""
        secret = config.get("secret")
        if not secret:
            return None
        name = config.get("name")
        try:
            payload = jwt.decode(credentials, secret, algorithms=[config["algorithm"]])
        except jwt.InvalidTokenError:
            return None
        return {
            "identity": payload.get("sub"),
            "tags": payload.get("tags", config["tags"]),
            "backend": f"jwt:{name}" if name else "jwt",
        }


if __name__ == "__main__":
    core = AuthCore(basic={"admin": {"password": "secret", "tags": "admin,ops"}})
    ok: Scope = {"headers": [(b"authorization", b"Basic " + _basic_auth_key("admin", "secret").encode())]}
    avatar = core.authenticate(ok)
    assert avatar is not None and avatar.identity == "admin"
    assert avatar.tags == ["admin", "ops"]
    assert core.authenticate({"headers": []}) is None
    bad: Scope = {"headers": [(b"authorization", b"Basic " + _basic_auth_key("admin", "wrong").encode())]}
    try:
        core.authenticate(bad)
    except HTTPUnauthorized as error:
        assert error.status == 401
        assert (b"www-authenticate", b"Bearer") in error.headers
    else:
        raise AssertionError("expected HTTPUnauthorized on wrong password")
    malformed: Scope = {"headers": [(b"authorization", b"Basicabc123")]}
    try:
        core.authenticate(malformed)
    except HTTPUnauthorized:
        pass
    else:
        raise AssertionError("expected HTTPUnauthorized on malformed header")
