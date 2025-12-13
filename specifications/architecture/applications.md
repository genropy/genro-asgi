# Applications Architecture

**Version**: 0.1.0
**Status**: 🔴 DA REVISIONARE
**Last Updated**: 2025-12-13

## Overview

Le **applications** (apps) sono componenti modulari che possono essere montati su `AsgiServer`. Ogni app è una unità autocontenuta che può avere:

- Propri routes
- Propria configurazione (`config.yaml`)
- Propri middleware
- Propri plugin

## Package Structure

```
src/genro_asgi/
└── applications/
    ├── __init__.py          # Exports: AsgiApplication, StaticSite
    ├── base.py              # AsgiApplication base class
    ├── static_site.py       # StaticSite (module-based app)
    └── static_site/         # StaticSite (path-based app)
        ├── __init__.py
        ├── app.py           # StaticSite class
        └── config.yaml      # Default configuration
```

## Base Class: AsgiApplication

```python
from genro_routes import RoutedClass

class AsgiApplication(RoutedClass):
    """Base class for apps mounted on AsgiServer."""
    pass
```

Tutte le app ereditano da `AsgiApplication`, che a sua volta eredita da `RoutedClass` (genro_routes). Questo fornisce:

- Sistema di routing via decoratore `@route`
- Metodi `get()` e `members()` per interrogare routes
- Integrazione automatica con il router del server

## App Configuration

### Due modi per configurare un'app

#### 1. Module-based (inline parameters)

```yaml
# server config.yaml
apps:
  docs:
    module: "genro_asgi:StaticSite"
    directory: "./public"
    name: "docs"
```

I parametri (`directory`, `name`) vengono passati al costruttore.

#### 2. Path-based (app directory)

```yaml
# server config.yaml
apps:
  docs:
    path: "./my_docs_app"
```

Dove `./my_docs_app/` contiene:

```
my_docs_app/
├── __init__.py      # Exports app class
├── app.py           # App implementation
└── config.yaml      # App configuration
```

### App config.yaml Structure

```yaml
# App-level configuration

# Basic settings
directory: "./public"
name: "docs"

# App-specific middleware (optional)
middleware:
  - type: "compression"
    level: 6
  - type: "cache"
    max_age: 3600

# App-specific plugins (optional)
plugins:
  - "my_plugin:MyPlugin"
```

## Middleware Resolution

Quando un'app ha middleware propri:

1. **Server middleware** si applicano a tutte le richieste
2. **App middleware** si applicano solo alle richieste per quell'app
3. Ordine: `Server middleware → App middleware → Handler`

```
Request → [Server CORS] → [Server Errors] → [App Compression] → Handler
```

## Plugin System

I plugin sono estensioni che aggiungono funzionalità all'app:

```yaml
plugins:
  - "auth:AuthPlugin"
  - module: "cache:CachePlugin"
    ttl: 300
```

I plugin vengono inizializzati all'avvio dell'app e hanno accesso al contesto dell'app.

## Built-in Applications

### StaticSite

App per servire file statici da una directory.

```python
class StaticSite(AsgiApplication):
    def __init__(self, directory: str | Path, name: str = "static"):
        self.directory = Path(directory)
        self.name = name
        self.router = StaticRouter(self.directory, name=name)
```

**Caratteristiche**:
- Usa `StaticRouter` internamente
- Supporta file di qualsiasi tipo
- MIME type detection automatica

## App Lifecycle

### Initialization

1. Server legge `apps:` dal config
2. Per ogni app:
   - Se `module:` → importa e istanzia con parametri inline
   - Se `path:` → legge `config.yaml` dalla directory, importa e istanzia
3. App viene attaccata al router del server

### Request Handling

1. Request arriva al server
2. Dispatcher identifica l'app dal path prefix
3. App middleware chain viene eseguita
4. Handler dell'app processa la richiesta
5. Response risale la chain

### Shutdown

1. Server riceve shutdown signal
2. Ogni app riceve evento `lifespan.shutdown`
3. App può fare cleanup (chiudere connessioni, flush cache, ecc.)

## Class Diagram

```
┌─────────────────┐
│   RoutedClass   │  (from genro_routes)
│   (abstract)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ AsgiApplication │
│   (base.py)     │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐  ┌─────────────┐
│  App1  │  │  StaticSite │
└────────┘  └─────────────┘
```

## See Also

- [Routing](../interview/answers/D-routing.md) - Come funziona il routing
- [Configuration](../interview/answers/E-configuration.md) - Sistema di configurazione
- [StaticRouter](../interview/answers/H-static-files.md) - Router per file statici
