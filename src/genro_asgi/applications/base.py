# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""AsgiApplication - Base class for ASGI applications."""

from __future__ import annotations

from genro_routes import RoutedClass  # type: ignore[import-untyped]

__all__ = ["AsgiApplication"]


class AsgiApplication(RoutedClass):
    """Base class for apps mounted on AsgiServer."""

    pass


if __name__ == "__main__":
    pass
