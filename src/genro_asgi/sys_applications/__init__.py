# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""System applications for genro-asgi.

These apps can be mounted via sys_apps config section.
They are loaded at /_sys/<name>/ paths.

Convention: each sys_app has {name}_app.py with class Application.
"""

from .genro_api import Application as GenroApiApp
from .swagger import Application as SwaggerApp

__all__ = ["GenroApiApp", "SwaggerApp"]
