# LocalStorage

Storage filesystem con API genro-storage compatibile.

## Classe

```python
class LocalStorage:
    def __init__(self, base_dir: str | Path | None = None):
        self._mounts: dict[str, Path] = {}
        self._base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
```

## Sintassi Path

```python
storage.node("site:resources/logo.png")           # mount:path
storage.node("site", "resources", "logo.png")     # parti separate
storage.node("site:resources", "images", "logo.png")  # mista
```

## Mount Predefiniti vs Configurati

### Predefiniti (metodo)
```python
def mount_site(self) -> Path:
    return self._base_dir
```

### Configurati (add_mount)
```python
storage.add_mount({"name": "uploads", "type": "local", "path": "/var/uploads"})
```

**Priorità**: metodi `mount_*` vincono su `_mounts` dict.

## LocalStorageNode API

| Property | Tipo | Descrizione |
|----------|------|-------------|
| `fullpath` | str | `"mount:path"` |
| `path` | str | path senza mount |
| `exists` | bool | esiste? |
| `isfile` | bool | è file? |
| `isdir` | bool | è directory? |
| `size` | int | bytes |
| `basename` | str | nome file |
| `suffix` | str | `.ext` |
| `mimetype` | str | MIME type |
| `parent` | Node | nodo parent |

| Metodo | Descrizione |
|--------|-------------|
| `read_bytes()` | legge bytes |
| `read_text(encoding)` | legge testo |
| `write_bytes(data)` | scrive bytes |
| `write_text(text)` | scrive testo |
| `child(*parts)` | nodo figlio |
| `children()` | lista figli |

## Subclass Custom

```python
class ProjectStorage(LocalStorage):
    def mount_cache(self) -> Path:
        return self._base_dir / ".cache"

    def mount_uploads(self) -> Path:
        return Path("/var/uploads")
```

## Decisioni

- **Solo local filesystem** - genro-storage per altri backend
- **Metodi prioritari** - `mount_*()` vince su config
- **Path relativi** - risolti rispetto a `_base_dir`
