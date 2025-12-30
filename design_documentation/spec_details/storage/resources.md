# ResourceLoader

Caricamento risorse gerarchico con fallback.

## Invariante "Dove + Cosa = Costante"

Per `/_resource/shop/tables/article?name=logo.png`:

| Livello | Dove (resources/) | Cosa (name) |
|---------|-------------------|-------------|
| article | article/resources/ | logo.png |
| tables | tables/resources/ | article/logo.png |
| shop | shop/resources/ | tables/article/logo.png |
| server | server/resources/ | shop/tables/article/logo.png |

## Strategie Composizione

### Override (default)
Immagini, HTML, JSON → primo trovato (più specifico) vince.

### Merge (CSS, JS)
`.css` e `.js` → concatenati dal generale allo specifico.

```
server/style.css   → primo
shop/style.css     → secondo
article/style.css  → terzo (finale)
```

## API

```python
class ResourceLoader:
    def load(self, *args, name: str) -> tuple[bytes, str] | None:
        """Carica risorsa. Ritorna (content, mime_type) o None."""
        levels = self.collect_levels(args)
        candidates = self.find_candidates(levels, args, name)
        return self.compose(candidates, name) if candidates else None
```

## Endpoint

```python
@route("root")
def load_resource(self, *args, name: str = ""):
    result = self.resource_loader.load(*args, name=name)
    if result is None:
        raise HTTPNotFound(f"Resource not found: {name}")
    content, mime_type = result
    return content
```

## resources_path

Ogni livello può avere `resources_path: Path | None`:
- Server: `base_dir / "resources"`
- App: `base_dir / "resources"`
- RoutingClass: custom

## Decisioni

- **Merge solo CSS/JS** - altri tipi override
- **Mount dinamici** - creati on-demand per ogni livello
- **Invariante costante** - dove + cosa sempre uguale
