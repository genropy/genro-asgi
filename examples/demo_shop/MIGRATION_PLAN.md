# Piano di Migrazione demo_shop: smartroute/smartpublisher → genro-asgi/genro-routes

**Versione**: 1.0.0
**Data**: 2025-12-15
**Status**: DA IMPLEMENTARE

---

## Obiettivo

Migrare l'esempio `demo_shop` dal vecchio stack (smartroute + smartpublisher) al nuovo stack (genro-asgi + genro-routes) mantenendo la stessa architettura e funzionalità.

---

## Documentazione di Riferimento (LEGGERE PRIMA)

Prima di iniziare, consultare obbligatoriamente:

### genro-asgi
- `docs/architecture/00-overview.md` - Architettura generale
- `docs/architecture/01-server.md` - AsgiServer, routing, dispatch
- `docs/architecture/08-routing.md` - Integrazione con genro-routes
- `src/genro_asgi/server.py` - Implementazione AsgiServer

### genro-routes
- `src/genro_routes/plugins/_base_plugin.py` - Interfaccia plugin (BasePlugin, MethodEntry)
- `src/genro_routes/core/router.py` - Router e attach_instance
- `src/genro_routes/__init__.py` - Export pubblici

### demo_shop attuale
- `examples/demo_shop/README.md` - Struttura e filosofia
- `examples/demo_shop/sample_shop/shop.py` - Shop class (aggregatore)
- `examples/demo_shop/sample_shop/sql/table.py` - Table base class con Router
- `examples/demo_shop/sample_shop/dbop_plugin.py` - Plugin per cursor/transaction
- `examples/demo_shop/published_shop/main.py` - Publisher attuale (da riscrivere)

---

## Architettura Target

```
AsgiServer (genro-asgi)
    │
    └── router (genro-routes Router)
            │
            └── shop (Shop come RoutingClass)
                    │
                    └── router
                            ├── types (ArticleTypes table)
                            ├── articles (Articles table)
                            └── purchases (Purchases table)
```

**Catena di istanze:**
```
AsgiServer
    └── self.shop = Shop(db_path)
            └── self.db = SqlDb(db_path, self)
                    └── self.tables["articles"] = Articles(db=self)
                            └── self.db = db  (ref a SqlDb)
                            └── self.api = Router + DbopPlugin
```

**Endpoint risultanti:**
- `GET /shop/types/list`
- `POST /shop/types/add`
- `GET /shop/articles/list`
- `POST /shop/articles/add`
- `GET /shop/articles/get/{id}`
- etc.

---

## File da Modificare

### 1. sample_shop/dbop_plugin.py (RISCRIVERE)

**Cambiamenti:**
- Import da `genro_routes` invece di `smartroute`
- Aggiungere `plugin_code` e `plugin_description` come attributi di classe
- Costruttore riceve `router` come primo argomento
- Registrazione plugin tramite `Router.register_plugin()`

**Vecchia interfaccia:**
```python
from smartroute import Router
from smartroute.plugins._base_plugin import BasePlugin, MethodEntry

class DbopPlugin(BasePlugin):
    def __init__(self, name: str | None = None, **config: Any):
        super().__init__(name=name or "dbop", **config)
```

**Nuova interfaccia:**
```python
from genro_routes import Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry

class DbopPlugin(BasePlugin):
    plugin_code = "dbop"
    plugin_description = "Database cursor injection and transaction management"

    def __init__(self, router: Any, **config: Any):
        super().__init__(router, **config)
```

**Metodo `wrap_handler`:** stessa firma, stessa logica.

---

### 2. sample_shop/sql/table.py (MODIFICARE IMPORT)

**Cambiamenti:**
- `from smartroute import Router, RoutingClass` → `from genro_routes import Router, RoutingClass`
- `from smartroute.plugins.pydantic import PydanticPlugin` → `from genro_routes.plugins.pydantic import PydanticPlugin`
- Aggiornare `PydanticExtrasPlugin` con `plugin_code` e `plugin_description`

**Nota:** La classe `Table` resta sostanzialmente uguale, cambia solo la derivazione.

---

### 3. sample_shop/tables/*.py (MODIFICARE IMPORT)

File interessati:
- `article_types.py`
- `articles.py`
- `purchases.py`

**Cambiamento:**
```python
# Vecchio
from smartroute import route

# Nuovo
from genro_routes import route
```

Il resto del codice (decoratori `@route`, metodi) resta identico.

---

### 4. published_shop/main.py (RISCRIVERE)

**Vecchio:**
```python
from smartpublisher import Publisher

class PublishedShop(Publisher):
    def __init__(self):
        super().__init__()
        self._shop = Shop(f"sqlite:{db_path}")
        self._mount_tables()

    def _mount_tables(self):
        for table_name in ("types", "articles", "purchases"):
            table = self._shop.db.table(table_name)
            self.api.add_child(table, name=table_name)
```

**Nuovo:**
```python
from genro_asgi import AsgiServer
from sample_shop.shop import Shop

class PublishedShop(AsgiServer):
    def __init__(self):
        super().__init__()
        db_path = Path(__file__).parent / "shop.db"
        self.shop = Shop(f"sqlite:{db_path}")
        self._mount_tables()

    def _mount_tables(self):
        for table_name in ("types", "articles", "purchases"):
            table = self.shop.db.table(table_name)
            self.router.attach_instance(table, name=table_name)

if __name__ == "__main__":
    server = PublishedShop()
    server.run()
```

---

### 5. config.yaml (OPZIONALE - NUOVO)

Se vogliamo usare la configurazione dichiarativa:

```yaml
server:
  host: "127.0.0.1"
  port: 8000

# Non serve apps: perché PublishedShop monta le table programmaticamente
```

---

## Ordine di Implementazione

### Fase 1: Plugin e Base Classes

1. **Riscrivere `dbop_plugin.py`**
   - Nuova interfaccia genro-routes
   - Testare che si registri correttamente

2. **Aggiornare `sql/table.py`**
   - Cambiare import
   - Aggiornare PydanticExtrasPlugin

### Fase 2: Table Classes

3. **Aggiornare `tables/article_types.py`**
   - Cambiare import route

4. **Aggiornare `tables/articles.py`**
   - Cambiare import route

5. **Aggiornare `tables/purchases.py`**
   - Cambiare import route

### Fase 3: Publisher

6. **Riscrivere `published_shop/main.py`**
   - Usare AsgiServer
   - Montare Shop con router.attach_instance

### Fase 4: Test e Verifica

7. **Testare l'applicazione**
   - Avviare il server
   - Verificare endpoint funzionanti
   - Testare CRUD operations

8. **Aggiornare README.md**
   - Documentare il nuovo stack
   - Aggiornare esempi di utilizzo

---

## Dipendenze

Il progetto richiede:
- `genro-asgi` (questo repository)
- `genro-routes` (da meta-genro-modules/sub-projects/genro-routes)
- `genro-toolbox` (per SmartOptions)
- `pydantic` (per validazione)

---

## Test di Verifica

Dopo la migrazione, verificare:

1. **Server si avvia:**
   ```bash
   cd examples/demo_shop/published_shop
   python main.py
   ```

2. **Endpoint rispondono:**
   ```bash
   # List types
   curl http://localhost:8000/types/list

   # Add type
   curl -X POST http://localhost:8000/types/add \
     -H "Content-Type: application/json" \
     -d '{"name": "electronics", "description": "Electronic devices"}'

   # List articles
   curl http://localhost:8000/articles/list
   ```

3. **Database operations funzionano:**
   - Insert con autocommit
   - Transaction con commit manuale
   - Rollback su errore

---

## Note Tecniche

### Pattern Catena Parent-Child

Ogni oggetto mantiene riferimento semantico al parent:
- `Table.db` → SqlDb
- `SqlDb.app` → Shop
- `Shop` (se montato) → AsgiServer via router

### DbopPlugin - Funzionamento

1. Handler ha `self.db` (Table eredita da RoutingClass, ha `self.db`)
2. Plugin intercetta chiamata
3. Inietta `cursor = self.db.cursor()` nei kwargs
4. Esegue handler
5. Se `autocommit=True` → `self.db.commit()`
6. Se eccezione → `self.db.rollback()`

### Nessun Globale

- Stato sempre in istanze
- `del server` → tutto garbage collected
- Test isolati possibili

---

## Checklist Finale

- [ ] dbop_plugin.py riscritto con nuova interfaccia
- [ ] sql/table.py aggiornato import
- [ ] PydanticExtrasPlugin aggiornato
- [ ] tables/article_types.py aggiornato import
- [ ] tables/articles.py aggiornato import
- [ ] tables/purchases.py aggiornato import
- [ ] published_shop/main.py riscritto con AsgiServer
- [ ] Server si avvia senza errori
- [ ] Endpoint /types/list funziona
- [ ] Endpoint /articles/add funziona
- [ ] README.md aggiornato

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
