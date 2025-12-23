# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Authentication backends for AuthMiddleware.

This package provides pluggable authentication backends.
Each backend handles a specific Authorization header scheme.

Exports:
    AuthBackend: ABC for custom backends
    BearerBackend: Handles "Authorization: Bearer <token>"
    BasicBackend: Handles "Authorization: Basic <base64>"
    BACKEND_REGISTRY: Dict mapping type name to backend class
"""

from .base import AuthBackend, BasicBackend, BearerBackend

BACKEND_REGISTRY: dict[str, type[AuthBackend]] = {
    "bearer": BearerBackend,
    "basic": BasicBackend,
}

__all__ = [
    "AuthBackend",
    "BasicBackend",
    "BearerBackend",
    "BACKEND_REGISTRY",
]
