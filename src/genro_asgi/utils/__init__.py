# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Utility classes for genro-asgi.

Exports:
    ServerBinder: Controlled interface to server resources.
    AsgiServerEnabler: Mixin for external apps that need server access.
    split_and_strip: Split comma-separated string and strip whitespace.
"""

from .binder import AsgiServerEnabler, ServerBinder


def split_and_strip(
    value: str | list[str] | None, default: list[str] | None = None
) -> list[str]:
    """Split comma-separated string and strip whitespace from each item.

    If value is already a list, returns a copy. If None, returns default.

    Examples:
        split_and_strip("a, b, c")  # ["a", "b", "c"]
        split_and_strip(["x", "y"])  # ["x", "y"]
        split_and_strip(None, ["default"])  # ["default"]
    """
    if value is None:
        return default if default is not None else []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",")]
    return list(value)


__all__ = ["AsgiServerEnabler", "ServerBinder", "split_and_strip"]
