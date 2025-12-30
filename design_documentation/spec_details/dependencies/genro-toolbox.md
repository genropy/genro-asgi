# genro-toolbox

Utilities condivise per l'ecosistema Genro.

## SmartOptions

Configurazione YAML con merge e override.

```python
from genro_toolbox import SmartOptions

config = SmartOptions(yaml_content)
config.middleware  # accesso attributo
config["middleware"]  # accesso dict
config.get("middleware", default={})
config.as_dict()  # converti a dict standard
```

### Merge con `+`

```yaml
# base.yaml
middleware:
  errors: on
  cors: off

# override.yaml
middleware:
  +cors: on  # merge invece di replace
```

## AppLoader

Caricamento isolato di moduli applicazione.

```python
from genro_toolbox import AppLoader

loader = AppLoader(base_dir="/path/to/apps")
cls = loader.load_class("shop:ShopApp")
# Equivalente a: from shop import ShopApp
```

Caratteristiche:
- Risolve path relativi a base_dir
- Carica moduli in modo isolato
- Cache per performance

## Altri Utilities

- `smartsuper` - Decoratore per chiamate parent semplificate
- `smartasync` - Utilities async/await
- Funzioni helper varie

## Uso in genro-asgi

```python
# server.py
from genro_toolbox import SmartOptions, AppLoader

class AsgiServer:
    def __init__(self, config_path):
        self.config = SmartOptions.from_file(config_path)
        self._app_loader = AppLoader()
```
