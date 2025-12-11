# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Data structures for ASGI applications.

This package provides Pythonic wrapper classes around raw ASGI data structures.
ASGI uses primitive types (bytes, tuples, dicts) for efficiency. These classes
add ergonomic APIs without sacrificing performance.

Mapping from ASGI to genro-asgi classes::

    ASGI Raw Data                          genro-asgi Classes
    ─────────────────                      ──────────────────
    scope["client"] = ("1.2.3.4", 80)      →  Address(host, port)
    scope["server"] = ("example.com", 443) →  Address(host, port)
    scope["headers"] = [(b"...", b"...")]  →  Headers (case-insensitive)
    scope["query_string"] = b"a=1&b=2"     →  QueryParams (parsed)
    "https://example.com/path?q=1"         →  URL (parsed)
    scope["state"] = {}                    →  State (attribute access)

Public Exports
==============
::

    from genro_asgi.datastructures import (
        Address,
        URL,
        Headers,
        QueryParams,
        State,
        headers_from_scope,
        query_params_from_scope,
    )

Modules
=======
- ``address``: Client/server address wrapper
- ``url``: URL parser with component access
- ``headers``: Case-insensitive HTTP headers
- ``query_params``: Parsed query string parameters
- ``state``: Request-scoped state container
"""

from .address import Address
from .headers import Headers, headers_from_scope
from .query_params import QueryParams, query_params_from_scope
from .state import State
from .url import URL

__all__ = [
    "Address",
    "URL",
    "Headers",
    "QueryParams",
    "State",
    "headers_from_scope",
    "query_params_from_scope",
]
