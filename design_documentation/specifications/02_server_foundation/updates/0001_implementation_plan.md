# 0001 - Piano di Implementazione Server App Separation

**Stato**: ✅ COMPLETATO
**Branch**: `feature/server-app-separation`
**Data inizio**: 2025-12-30
**Riferimento**: [0001_server_app_separation.md](./0001_server_app_separation.md)

---

## Panoramica

Separazione tra `AsgiServer` (orchestratore) e `ServerApp` (endpoint di sistema).

**Struttura semplificata:**

```text
src/genro_asgi/
├── _server_app.py          # Singolo modulo (NON package)
├── server.py               # AsgiServer senza endpoint
└── resources/              # Risorse di ServerApp (già esistente)
    └── html/
        └── default_index.html
```

**Nota**: `resources/` è semanticamente di `ServerApp` - nessuno spostamento necessario.

---

## Step 1: Creare `_server_app.py`

**File:** `src/genro_asgi/_server_app.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ServerApp - System endpoints for AsgiServer.

Endpoint di sistema:
- index: pagina default con redirect a main_app
- _openapi: schema OpenAPI del server
- _resource: loader risorse con fallback gerarchico
- _create_jwt: creazione JWT (richiede superadmin)

Montato automaticamente come /_server/ dal server.
Modulo privato - non esportato in __init__.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from genro_routes import RoutingClass, Router, route  # type: ignore[import-untyped]

from .exceptions import HTTPNotFound, Redirect

if TYPE_CHECKING:
    from .server import AsgiServer

__all__ = ["ServerApp"]


class ServerApp(RoutingClass):
    """System endpoints for AsgiServer. Mounted at /_server/."""

    __slots__ = ("_server", "main")

    def __init__(self, server: AsgiServer) -> None:
        """Initialize ServerApp with reference to parent server."""
        self._server = server
        self.main = Router(self, name="main")

    @property
    def config(self) -> Any:
        """Server configuration."""
        return self._server.config

    @property
    def main_app(self) -> str | None:
        """Return main app name: configured or single app."""
        configured: str | None = self.config["main_app"]
        if configured:
            return configured
        apps: dict[str, Any] = self.config["apps"] or {}
        return next(iter(apps)) if len(apps) == 1 else None

    @route(meta_mime_type="text/html")
    def index(self) -> str:
        """Default index page. Redirects to main_app if configured."""
        if self.main_app:
            raise Redirect(f"/{self.main_app}/")
        # resources/ è nella stessa directory di questo modulo
        html_path = Path(__file__).parent / "resources" / "html" / "default_index.html"
        return html_path.read_text()

    @route(meta_mime_type="application/json")
    def _openapi(self, *args: str) -> dict[str, Any]:
        """OpenAPI schema endpoint."""
        basepath = "/".join(args) if args else None
        paths = self._server.router.nodes(basepath=basepath, mode="openapi")
        return {
            "openapi": "3.1.0",
            "info": self._server.openapi_info,
            **paths,
        }

    @route(name="_resource")
    def load_resource(self, *args: str, name: str) -> Any:
        """Load resource with hierarchical fallback."""
        result = self._server.resource_loader.load(*args, name=name)
        if result is None:
            raise HTTPNotFound(f"Resource not found: {name}")
        content, mime_type = result
        return self.result_wrapper(content, mime_type=mime_type)

    @route(auth_tags="superadmin&has_jwt")
    def _create_jwt(
        self,
        jwt_config: str | None = None,
        sub: str | None = None,
        tags: str | None = None,
        exp: int | None = None,
        **extra_kwargs: Any,
    ) -> dict[str, Any]:
        """Create JWT token via HTTP endpoint. Requires superadmin auth tag."""
        if not jwt_config or not sub:
            return {"error": "jwt_config and sub are required"}
        _ = (tags, exp, extra_kwargs)  # unused until genro-toolbox is ready
        return {"error": "not implemented - waiting for genro-toolbox"}


if __name__ == "__main__":
    print("ServerApp requires AsgiServer instance")
```

---

## Step 2: Aggiornare `server.py`

### 2.1 Nuovi slots

```python
__slots__ = (
    "apps",
    "router",
    "config",
    "base_dir",
    "logger",
    "lifespan",
    "request_registry",
    "dispatcher",
    "storage",
    "resource_loader",
    "openapi_info",
    "app_loader",
    # NUOVI
    "server_app",     # ServerApp - endpoint di sistema
    "sys_apps",       # dict[str, RoutingClass] - app di sistema
    "_sys_container", # Container per sys_apps
)
```

### 2.2 Nel `__init__`

```python
from ._server_app import ServerApp

# Dopo la creazione del router:

# Server app - endpoint di sistema
self.server_app = ServerApp(server=self)
self.router.attach_instance(self.server_app, name="_server")

# System apps container (per future sys_apps)
self.sys_apps: dict[str, RoutingClass] = {}
self._sys_container = RoutingClass()
self._sys_container.main = Router(self._sys_container, name="main")
self.router.attach_instance(self._sys_container, name="_sys")

# TODO: loading sys_apps da config (quando implementato)
# for name, spec in self.config.get_sys_app_specs_raw().items():
#     ...

# Router default entry punta a server_app.index
self.router.default_entry = "_server/index"
```

### 2.3 Rimuovere da server.py

- `main_app` property
- `index()` method
- `_openapi()` method
- `load_resource()` method
- `_create_jwt()` method
- `resources_path` property (opzionale, valutare)

---

## Step 3: Aggiornare `server_config.py`

### 3.1 Property `sys_apps`

```python
@property
def sys_apps(self) -> SmartOptions | None:
    """System apps configuration."""
    result: SmartOptions | None = self._opts["sys_apps"]
    return result
```

### 3.2 Metodo `get_sys_app_specs_raw()`

```python
def get_sys_app_specs_raw(self) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """Return {name: (module_name, class_name, kwargs)} for system apps."""
    if not self.sys_apps:
        return {}
    result: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for name, app_opts in self.sys_apps.as_dict().items():
        module_path, kwargs = self._parse_app_opts(name, app_opts)
        module_name, class_name = module_path.split(":")
        result[name] = (module_name, class_name, kwargs)
    return result
```

---

## Step 4: Test

### 4.1 `tests/test_server_app.py`

```python
"""Tests for ServerApp."""

from unittest.mock import MagicMock

from genro_asgi._server_app import ServerApp


class TestServerApp:
    """Test ServerApp functionality."""

    def test_init_requires_server(self):
        """ServerApp requires server instance."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": {}}
        app = ServerApp(mock_server)
        assert app._server is mock_server

    def test_main_app_configured(self):
        """Return configured main_app."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": "shop", "apps": {"shop": {}}}
        app = ServerApp(mock_server)
        assert app.main_app == "shop"

    def test_main_app_single(self):
        """Return single app as main_app."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": {"shop": {}}}
        app = ServerApp(mock_server)
        assert app.main_app == "shop"

    def test_main_app_multiple_none(self):
        """Return None when multiple apps and no main_app configured."""
        mock_server = MagicMock()
        mock_server.config = {"main_app": None, "apps": {"shop": {}, "api": {}}}
        app = ServerApp(mock_server)
        assert app.main_app is None
```

---

## Step 5: Documentazione

### 5.1 Aggiornare `04_dispatcher.md`

Aggiungere sezione sul nuovo routing tree con `_server/` e `_sys/`.

### 5.2 Aggiornare proposta 0001

Cambiare stato da 📋 PROPOSTA a ✅ IMPLEMENTATO.

---

## Checklist Finale

- [ ] Step 1: `_server_app.py` creato
- [ ] Step 2: `server.py` aggiornato
- [ ] Step 3: `server_config.py` aggiornato
- [ ] Step 4: Test passano
- [ ] Step 5: Documentazione aggiornata
- [ ] ruff check passa
- [ ] mypy passa
- [ ] pytest passa

---

## Backward Compatibility

Per mantenere i vecchi path (`/_openapi` invece di `/_server/_openapi`):

```python
# Alias route in server.py (temporaneo)
@route("root")
def _openapi(self, *args: str) -> dict[str, Any]:
    """Backward compatibility alias."""
    return self.server_app._openapi(*args)
```

**Decisione**: Valutare se necessario. Se nessun codice usa i vecchi path, non implementare.

---

**Ultimo aggiornamento**: 2025-12-30
