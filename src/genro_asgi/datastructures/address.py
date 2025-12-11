# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Address wrapper for ASGI client/server tuples.

Purpose
=======
Wraps the ``(host, port)`` tuple used in ASGI scope for ``client`` and
``server`` fields. Provides named attribute access instead of tuple indexing.

ASGI Mapping::

    scope["client"] = ("1.2.3.4", 80)    →  Address(host, port)
    scope["server"] = ("example.com", 443) →  Address(host, port)

Definition::

    class Address:
        __slots__ = ("host", "port")

        def __init__(self, host: str, port: int) -> None
        def __repr__(self) -> str
        def __eq__(self, other: object) -> bool
            # Compares with Address or tuple (for ASGI compatibility)

Example::

    from genro_asgi.datastructures import Address

    client = Address("192.168.1.1", 54321)
    print(client.host)  # "192.168.1.1"
    print(client.port)  # 54321

    # Comparison with ASGI tuple
    assert client == ("192.168.1.1", 54321)

Design Notes
============
- Uses ``__slots__`` for memory efficiency
- Compares equal to ``tuple[str, int]`` for ASGI compatibility
- No ``__hash__`` (can be added if dict key usage is needed)
- No ``__iter__`` (use explicit attribute access)
"""

__all__ = ["Address"]


class Address:
    """
    Client or server address wrapper.

    Wraps the ``(host, port)`` tuple used in ASGI scope for ``client`` and
    ``server`` fields. Provides named attribute access instead of tuple indexing.

    Attributes:
        host: The hostname or IP address.
        port: The port number.

    Example:
        >>> addr = Address("192.168.1.1", 8080)
        >>> addr.host
        '192.168.1.1'
        >>> addr.port
        8080
        >>> addr == ("192.168.1.1", 8080)  # Compare with ASGI tuple
        True
    """

    __slots__ = ("host", "port")

    def __init__(self, host: str, port: int) -> None:
        """
        Initialize an Address.

        Args:
            host: The hostname or IP address.
            port: The port number.
        """
        self.host = host
        self.port = port

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"Address(host={self.host!r}, port={self.port})"

    def __eq__(self, other: object) -> bool:
        """
        Compare with another Address or tuple.

        Supports comparison with ASGI-style tuples for backward compatibility.

        Args:
            other: An Address instance or a ``(host, port)`` tuple.

        Returns:
            True if host and port match, False otherwise.
        """
        if isinstance(other, Address):
            return self.host == other.host and self.port == other.port
        if isinstance(other, tuple) and len(other) == 2:
            return bool(self.host == other[0] and self.port == other[1])
        return False
