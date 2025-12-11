"""
Example of PYTHONIC usage - NO smpub required!

This demonstrates that the Shop class is a normal Python class
that can be used directly in any Python context.

smpub is NOT needed for this - it's just regular Python code.

Run with: python -m examples.sample_shop.example_pythonic
"""

# Use try/except for flexible imports
try:
    from examples.sample_shop import Shop
except ImportError:
    from . import Shop


def main():
    """Example of using Shop class directly in Python."""

    # Instantiate shop - this is just a normal Python object
    shop = Shop()

    print("=" * 60)
    print("PYTHONIC USAGE - No smpub, just regular Python!")
    print("=" * 60)
    print()

    # 1. Add article types
    print("1. Adding article types...")
    result = shop.types.add("electronics", "Electronic devices")
    print(f"   {result.get('message', result.get('error', 'OK'))}")

    result = shop.types.add("furniture", "Furniture items")
    print(f"   {result.get('message', result.get('error', 'OK'))}")
    print()

    # 2. List article types
    print("2. Listing article types...")
    result = shop.types.list()
    for t in result["types"]:
        print(f"   - {t['name']}: {t['description']}")
    print()

    # 3. Add articles
    print("3. Adding articles...")
    result = shop.articles.add(
        article_type_id=1, code="LAPTOP001", description="MacBook Pro 16", price=2499.00
    )
    print(f"   {result.get('message', result.get('error', 'OK'))}")

    result = shop.articles.add(
        article_type_id=2, code="BOOK001", description="Python Programming", price=49.99
    )
    print(f"   {result.get('message', result.get('error', 'OK'))}")
    print()

    # 4. List articles
    print("4. Listing articles...")
    result = shop.articles.list()
    for article in result["articles"]:
        print(f"   - {article['code']}: {article['description']} (${article['price']})")
    print()

    # 5. Add purchases
    print("5. Adding purchases...")
    result = shop.purchases.add(article_id=1, quantity=2)
    print(f"   {result.get('message', result.get('error', 'OK'))}")

    result = shop.purchases.add(article_id=2, quantity=5)
    print(f"   {result.get('message', result.get('error', 'OK'))}")
    print()

    # 6. Get statistics
    print("6. Purchase statistics...")
    result = shop.purchases.statistics()
    print(f"   Total purchases: {result['total_purchases']}")
    print(f"   Total revenue: ${result['total_revenue']:.2f}")
    print()

    # 7. Using convenience methods
    print("7. Using convenience methods on Shop...")
    result = shop.add_type("toys", "Toys and games")
    print(f"   {result.get('message', result.get('error', 'OK'))}")

    stats = shop.get_statistics()
    print(f"   Revenue: ${stats['total_revenue']:.2f}")
    print()

    print("=" * 60)
    print("This is NORMAL Python - no CLI, no HTTP, no smpub!")
    print("The classes work perfectly fine on their own.")
    print("=" * 60)


if __name__ == "__main__":
    main()
