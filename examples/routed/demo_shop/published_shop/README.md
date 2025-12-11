# Published Shop - smpub Publishing Example

This example demonstrates how to **publish** an existing Python class with smpub.

## Key Concept

The [sample_shop](../sample_shop) module is a **standalone Python library** that works perfectly fine on its own.

**This folder shows how to OPTIONALLY publish it** for CLI/HTTP access using smpub.

## What's Here

Just one file: `main.py` - the smpub publisher.

That's it! The actual Shop implementation is in `sample_shop/` - this just publishes it.

## Structure

```text
published_shop/
└── main.py          # ONLY the publisher - imports Shop from sample_shop
```

The actual implementation:
```text
sample_shop/         # The REAL code - standalone Python library
├── tables/          # Normal Python classes
├── shop.py          # Aggregates table managers
└── ...
```

## Usage

### CLI Mode

```bash
# From this directory
python main.py types list
python main.py articles add --article-type-id 1 --code "ABC" --description "..." --price 99.99
python main.py purchases statistics
```

### HTTP Mode

```bash
# Start server
python main.py --mode http

# Use API
curl -X POST http://localhost:8000/api/v1/types/list
curl -X POST http://localhost:8000/api/v1/articles/add \
  -H "Content-Type: application/json" \
  -d '{"article_type_id": 1, "code": "ABC", "description": "...", "price": 99.99}'
```

## How It Works

```python
# main.py is tiny - just imports and publishes!

from smartpublisher import Publisher
from sample_shop import Shop  # ← Import existing class

class ShopApp(Publisher):
    def __init__(self):
        super().__init__()
        shop = Shop()  # ← Instantiate normal Python class

        # Publish for CLI/HTTP
        self.publish(shop.types, prefix="types")
        self.publish(shop.articles, prefix="articles")
        self.publish(shop.purchases, prefix="purchases")
```

## The Point

**smpub is a thin layer** that takes existing Python classes and exposes them via CLI/HTTP.

The Shop class doesn't know about smpub. It's just a normal Python class.

See [sample_shop](../sample_shop) for:
- Pure Python usage (`example_pythonic.py`)
- Interactive Jupyter notebook (`shop_usage.ipynb`)
- Implementation details
