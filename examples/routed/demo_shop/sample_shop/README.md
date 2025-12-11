# Sample Shop - E-commerce Example

Complete example of an e-commerce shop management system using smpub with SQLite backend.

**See [../PLUGINS_EXPLANATION.md](../PLUGINS_EXPLANATION.md) for details on how smartswitch plugins reduce boilerplate code.**

## Key Concept

**The Shop class is a NORMAL Python class** - it works perfectly fine without smpub!

- ✅ Use it directly in Python code (see `example_pythonic.py`)
- ✅ Optionally publish it with smpub for CLI/HTTP access (see `main.py`)

smpub is a **publisher**, not a requirement. The classes use smartswitch for method dispatch and validation, but they're just regular Python objects.

## Project Structure

```text
examples/
├── PLUGINS_EXPLANATION.md   # How plugins reduce boilerplate (shared across examples)
│
├── sample_shop/             # Standalone Python library
│   ├── database.py          # Database schema and connection
│   ├── tables/              # Table handler classes (normal Python classes)
│   │   ├── article_types.py # ArticleTypes manager
│   │   ├── articles.py      # Articles manager
│   │   └── purchases.py     # Purchases manager
│   ├── shop.py              # Shop class (aggregates table managers)
│   ├── example_pythonic.py  # Pure Python usage examples
│   ├── shop_usage.ipynb     # Jupyter notebook with interactive examples
│   └── README.md
│
└── published_shop/          # OPTIONAL smpub publishing (separate folder!)
    ├── main.py              # Publisher (imports Shop from sample_shop)
    └── README.md            # Publishing examples
```

**Notice**: The publisher is in a **separate folder** to emphasize that it's optional!

## Features

- **Article Types Management** (`ArticleTypes`): Manage categories (shoes, clothing, books)
- **Articles Management** (`Articles`): Manage products with code, description, price
- **Purchases Management** (`Purchases`): Track purchases with quantity and totals
- **Shop Class**: Aggregates all managers - works standalone OR can be published

## Database Schema

```text
article_types
├── id (PK)
├── name (unique)
└── description

articles
├── id (PK)
├── article_type_id (FK)
├── code (unique)
├── description
└── price

purchases
├── id (PK)
├── article_id (FK)
├── quantity
└── purchase_date (timestamp)
```

## Usage

### 1. Pure Python Usage (NO smpub required)

```python
# This is just normal Python - no CLI, no HTTP, no smpub!
from sample_shop import Shop

shop = Shop()

# Add article types
shop.types.add("electronics", "Electronic devices")
shop.types.add("books", "Books and publications")

# Add articles
shop.articles.add(
    article_type_id=1,
    code="LAPTOP001",
    description="MacBook Pro 16",
    price=2499.00
)

# Add purchases
shop.purchases.add(article_id=1, quantity=2)

# Get statistics
stats = shop.purchases.statistics()
print(f"Revenue: ${stats['total_revenue']:.2f}")

# Or use convenience methods
shop.add_type("clothing", "Clothing items")
shop.add_purchase(article_id=1, quantity=5)
```

**Run the pythonic example:**

```bash
python example_pythonic.py
```

**Or explore interactively:**

```bash
jupyter notebook shop_usage.ipynb
```

This demonstrates that the Shop class works perfectly fine on its own!

### 2. CLI/HTTP Mode (OPTIONAL - with smpub)

The Shop class can be **optionally published** for CLI/HTTP access.

**See [../published_shop](../published_shop) for the publisher example.**

The publisher is in a **separate folder** to emphasize it's optional!

## Key Design Patterns

### 1. Clean Class Design

Classes are written as normal Python classes without awareness of publication:

```python
class Articles:
    def add(self, article_type_id: int, code: str, description: str, price: float) -> dict:
        """Add a new article."""
        # Business logic here
```

No `PublishedClass` inheritance, no `handler_` prefix needed.

### 2. Type Hints for Validation

Type hints in method signatures drive automatic Pydantic validation:

```python
def add(self, article_type_id: int, code: str, description: str, price: float) -> dict:
    # article_type_id will be validated as int
    # code and description as str
    # price as float
```

### 3. Field Constraints for Advanced Validation

Use Pydantic Field for constraints without manual checks:

```python
from typing import Annotated
from pydantic import Field

def add(
    self,
    article_id: int,
    quantity: Annotated[int, Field(gt=0, description="Quantity must be > 0")]
) -> dict:
    # PydanticPlugin validates quantity > 0 automatically
    # No need for: if quantity <= 0: return {"error": ...}
```

### 4. Business Logic First

Validation logic is declarative (in type hints), not imperative:

```python
# BEFORE (manual validation):
def add(self, price: float):
    if price <= 0:
        return {"success": False, "error": "Price must be > 0"}
    # ... business logic

# AFTER (declarative validation):
def add(self, price: Annotated[float, Field(gt=0)]):
    # ... business logic only
```

### 5. Database Context Manager

Clean resource management with context managers:

```python
with get_connection() as conn:
    cursor = conn.cursor()
    # ... database operations
```

### 6. Consistent Return Format

All methods return dictionaries with `success` flag:

```python
return {
    "success": True,
    "id": cursor.lastrowid,
    "message": "..."
}
```

## Code Savings Example

Compare article validation WITH and WITHOUT smartswitch:

### Without smartswitch PydanticPlugin (manual)

```python
def add(self, article_type_id, code, description, price):
    # Type validation
    if not isinstance(article_type_id, int):
        return {"success": False, "error": "article_type_id must be int"}
    if not isinstance(code, str):
        return {"success": False, "error": "code must be str"}
    if not isinstance(description, str):
        return {"success": False, "error": "description must be str"}
    if not isinstance(price, (int, float)):
        return {"success": False, "error": "price must be number"}

    # Constraint validation
    if price <= 0:
        return {"success": False, "error": "price must be > 0"}

    # Finally, business logic
    with get_connection() as conn:
        # ... actual work
```

### With smartswitch PydanticPlugin (automatic)

```python
def add(
    self,
    article_type_id: int,
    code: str,
    description: str,
    price: Annotated[float, Field(gt=0)]
) -> dict:
    # Business logic directly - validation handled by plugin!
    with get_connection() as conn:
        # ... actual work
```

**Savings**: 10+ lines of boilerplate per method × dozens of methods = hundreds of lines saved!

## Testing

```bash
# Run the example
cd /path/to/smpub/examples/sample_shop
python main.py types list
```

## Notes

- Database is automatically created on first run
- Pre-populated with 3 article types (shoes, clothing, books)
- Foreign key constraints prevent orphaned records
- Timestamps automatically tracked for purchases
- Statistics method provides aggregated insights
- All validation happens declaratively via type hints
