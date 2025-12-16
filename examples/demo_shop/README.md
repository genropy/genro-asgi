# Demo Shop

Esempio di applicazione genro-asgi che dimostra:
- RoutedClass con Router aggregato
- Gestione tabelle SQL con pattern `configure()`
- Auto-discovery delle tabelle
- Integrazione Swagger/OpenAPI

## Avvio

```bash
python -m genro_asgi serve examples/demo_shop
```

Server disponibile su `http://127.0.0.1:8000`

## Endpoints

### API Shop
- `POST /shop/info` - Info sullo shop e tabelle disponibili

### Tabelle
Ogni tabella espone operazioni CRUD:

**Article Type** (`/shop/article_type/`)
- `add` - Crea tipo articolo
- `get` - Recupera per id
- `list` - Lista tutti
- `remove` - Elimina per id

**Article** (`/shop/article/`)
- `add` - Crea articolo
- `get` - Recupera per id
- `list` - Lista tutti
- `remove` - Elimina per id
- `update_price` - Aggiorna prezzo

**Purchase** (`/shop/purchase/`)
- `add` - Registra acquisto
- `get` - Recupera per id
- `list` - Lista tutti
- `remove` - Elimina per id
- `statistics` - Statistiche acquisti

### Swagger UI
- `/_swagger` - Documentazione di tutto il server
- `/_swagger?app=shop` - Documentazione solo dello Shop

## Struttura

```
demo_shop/
├── config.yaml              # Configurazione server
├── sample_shop/
│   ├── shop.py              # Shop - RoutedClass principale
│   ├── sql/
│   │   ├── __init__.py      # Esporta Table, SqlDb, tipi colonna
│   │   ├── column.py        # Column e Columns (definizione schema)
│   │   ├── table.py         # Table base class con configure() hook
│   │   ├── db.py            # SqlDb - gestione database
│   │   └── adapters/
│   │       ├── base.py      # DbAdapter con CRUD helpers
│   │       ├── sqlite.py    # SQLite adapter
│   │       └── postgres.py  # PostgreSQL adapter (stub)
│   └── tables/
│       ├── article_type.py  # Tabella tipi articolo
│       ├── article.py       # Tabella articoli
│       └── purchase.py      # Tabella acquisti
└── README.md
```

## Pattern implementati

### 1. Table con configure() hook

```python
class Article(Table):
    name = "article"
    name_long = "Article"
    name_plural = "Articles"

    def configure(self):
        c = self.columns
        c.column("id", Integer, primary_key=True, autoincrement=True)
        c.column("article_type_id", Integer).relation(table="article_type")
        c.column("code", String, unique=True)
        c.column("description", String)
        c.column("price", Float)
```

### 2. Relazioni (logiche o SQL)

```python
# Solo logica (default)
c.column("article_id", Integer).relation(table="article")

# Con FOREIGN KEY constraint SQL
c.column("article_id", Integer).relation(table="article", sql=True)
```

### 3. CRUD helpers in DbAdapter

```python
# Insert
row_id = self.db.adapter.insert(self.name, cursor, code=code, price=price)

# Select
records = self.db.adapter.select(self.name, cursor)
record = self.db.adapter.select_one(self.name, cursor, where={"id": id})

# Update
self.db.adapter.update(self.name, cursor, values={"price": new_price}, where={"id": id})

# Delete
self.db.adapter.delete(self.name, cursor, where={"id": id})

# Exists
if self.db.adapter.exists(self.name, cursor, where={"code": code}):
    return self._error("Already exists")
```

### 4. Auto-discovery tabelle

Shop scopre automaticamente le classi Table in `tables/`:

```python
def _configure_tables(self) -> list[type[Table]]:
    tables_dir = Path(__file__).parent / "tables"
    for py_file in tables_dir.glob("*.py"):
        # importa e trova subclass di Table
```

### 5. OpenAPI automatico

Ogni RoutedClass con `title` e `version` espone schema OpenAPI:

```python
class Shop(RoutedClass):
    title = "Shop API"
    version = "1.0.0"
```

Accessibile via `/_swagger?app=shop` o `/_openapi_json?app=shop`

## Database

SQLite in-memory o file. Schema creato automaticamente al primo avvio.

```yaml
# config.yaml
apps:
  shop:
    module: "sample_shop.shop:Shop"
    connection_string: "sqlite:shop.db"
```
