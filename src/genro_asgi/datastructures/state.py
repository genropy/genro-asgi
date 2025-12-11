# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Request-scoped state container with attribute access.

Purpose
=======
Uses magic attribute methods (``__getattr__``/``__setattr__``) to provide
ergonomic attribute-style access while storing data in an internal dict.
This is a standard pattern used by Starlette, Flask, and other frameworks.

ASGI Mapping::

    scope["state"] = {}  →  State (attribute access)

Definition::

    class State:
        __slots__ = ("_state",)

        def __init__(self) -> None
        def __setattr__(self, name: str, value: Any) -> None
        def __getattr__(self, name: str) -> Any
        def __delattr__(self, name: str) -> None
        def __contains__(self, name: object) -> bool
        def __repr__(self) -> str

Example::

    from genro_asgi.datastructures import State

    state = State()
    state.user_id = 123
    state.is_authenticated = True

    print(state.user_id)          # 123
    print("user_id" in state)     # True
    print("missing" in state)     # False

    del state.user_id
    # state.user_id  # Raises AttributeError

Design Notes
============
- Uses ``__slots__`` for memory efficiency
- Uses ``object.__setattr__`` in ``__init__`` to bypass custom ``__setattr__``
- Missing attributes raise ``AttributeError`` (not ``KeyError``)
- Standard pattern from Starlette, Flask, Werkzeug
"""

from typing import Any

__all__ = ["State"]


class State:
    """
    Request-scoped state container with attribute access.

    Provides ergonomic attribute-style access to request state, commonly used
    by middleware to attach data (e.g., authenticated user, request ID).

    Uses Python's magic attribute methods (``__getattr__``/``__setattr__``) to
    store data in an internal dictionary while providing ``state.attr`` syntax.
    This is a standard pattern used by Starlette, Flask, and other frameworks.

    Example:
        >>> state = State()
        >>> state.user_id = 123
        >>> state.is_authenticated = True
        >>> state.user_id
        123
        >>> "user_id" in state
        True
        >>> del state.user_id
        >>> "user_id" in state
        False

        # Missing attributes raise AttributeError
        >>> state.missing  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        AttributeError: State has no attribute 'missing'
    """

    __slots__ = ("_state",)

    def __init__(self) -> None:
        """
        Initialize an empty State container.

        Uses ``object.__setattr__`` to initialize the internal dict without
        triggering our custom ``__setattr__`` override.
        """
        object.__setattr__(self, "_state", {})

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Set a state attribute.

        Args:
            name: Attribute name.
            value: Value to store.
        """
        self._state[name] = value

    def __getattr__(self, name: str) -> Any:
        """
        Get a state attribute.

        Args:
            name: Attribute name.

        Returns:
            The stored value.

        Raises:
            AttributeError: If attribute does not exist.
        """
        try:
            return self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'") from None

    def __delattr__(self, name: str) -> None:
        """
        Delete a state attribute.

        Args:
            name: Attribute name to delete.

        Raises:
            AttributeError: If attribute does not exist.
        """
        try:
            del self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'") from None

    def __contains__(self, name: object) -> bool:
        """Check if attribute exists in state."""
        if not isinstance(name, str):
            return False
        return name in self._state

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"State({self._state!r})"
