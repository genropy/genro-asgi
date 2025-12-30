# WSGI Migration

Strategia per migrazione da Genropy WSGI legacy.

## Stato

📋 **PIANIFICATO** - Dipende da completamento core genro-asgi

## Obiettivo

Permettere migrazione graduale da applicazioni Genropy WSGI esistenti verso genro-asgi mantenendo compatibilità.

## Sfide

1. **API diverse** - WSGI vs ASGI paradigmi
2. **Sync vs Async** - Legacy code è sincrono
3. **State management** - Pattern diversi
4. **Session/Avatar** - API diverse

## Strategia Proposta

### Fase 1: Wrapper WSGI→ASGI

```python
from genro_asgi.compat import wsgi_to_asgi

legacy_app = load_wsgi_app()
asgi_app = wsgi_to_asgi(legacy_app)
```

Wrapper che esegue WSGI in thread pool.

### Fase 2: Adapters

Adapters per classi comuni:
- `LegacyRequest` → `HttpRequest`
- `LegacyResponse` → `Response`
- `LegacySession` → `Session`

### Fase 3: Hybrid Mode

```python
class HybridApplication(AsgiApplication):
    def __init__(self, legacy_handler):
        self.legacy = legacy_handler

    @route("/legacy/{path:path}")
    async def legacy_fallback(self, path):
        return await self.run_legacy(path)
```

### Fase 4: Gradual Migration

Migrare endpoint per endpoint:
1. Nuovi endpoint in genro-asgi
2. Legacy endpoint via adapter
3. Graduale riscrittura

## Compatibilità

| Feature | Supporto |
|---------|----------|
| Request/Response | ✅ Via adapters |
| Session | ⚠️ Parziale |
| Avatar | ⚠️ Parziale |
| GnrTable | ❌ Richiede genro-orm |
| Bag | ✅ Via genro-bag |

## Timeline

Dopo stabilizzazione core genro-asgi:
1. Wrapper base: 1 settimana
2. Adapters: 2 settimane
3. Hybrid mode: 1 settimana
4. Testing con app reale: ongoing

## Note

La migrazione completa richiede anche:
- genro-orm per database
- genro-bag per Bag datastructure
- Documentazione migration guide
