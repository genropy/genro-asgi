# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""System applications for genro-asgi.

These apps can be mounted via sys_apps config section.
They are loaded at /_sys/<name>/ paths.

Convention: each sys_app has {name}_app.py with class Application.
Access via subpackage: swagger.Application, genro_api.Application.
"""

from . import genro_api, swagger

__all__ = ["genro_api", "swagger"]
