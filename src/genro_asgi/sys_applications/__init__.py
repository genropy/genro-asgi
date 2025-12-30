# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""System applications for genro-asgi.

These apps can be mounted via sys_apps config section.
They are loaded at /_sys/<name>/ paths.
"""

from .genro_api import GenroApiApp
from .swagger import SwaggerApp

__all__ = ["GenroApiApp", "SwaggerApp"]
