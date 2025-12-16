# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Application classes for genro-asgi.

Exports:
    AsgiApplication: Base class for apps mounted on AsgiServer.
    SwaggerApp: OpenAPI/Swagger documentation app.
    GenroApiApp: Custom API Explorer app (Shoelace).
"""

from .base import AsgiApplication
from .genro_api import GenroApiApp
from .swagger import SwaggerApp

__all__ = ["AsgiApplication", "GenroApiApp", "SwaggerApp"]
