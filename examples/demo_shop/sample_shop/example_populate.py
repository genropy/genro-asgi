#!/usr/bin/env python3
"""Example: Populate database with sample data and show statistics."""

from .shop import Shop

# Create shop instance
shop = Shop("sqlite:shop_demo.db")

print("=" * 60)
print("POPULATING DATABASE")
print("=" * 60)

# Populate database
result = shop.populateDb()

print(f"\n✓ Created {result['types']} article types")
print(f"✓ Created {result['articles']} articles")
print(f"✓ Created {result['purchases']} purchases")

print("\n" + "=" * 60)
print("ARTICLE TYPES")
print("=" * 60)

# List article types
types = shop.db.table("types").list()
for t in types["types"]:
    print(f"\n{t['name'].upper()}")
    print(f"  Description: {t['description']}")

print("\n" + "=" * 60)
print("TOP ARTICLES BY PURCHASES")
print("=" * 60)

# Get statistics
stats = shop.db.table("purchases").statistics()
print(f"\nTotal Purchases: {stats['total_purchases']}")
print(f"Total Revenue: ${stats['total_revenue']:.2f}")

print("\nTop 5 Most Purchased Articles:")
for i, article in enumerate(stats["top_articles"][:5], 1):
    print(f"\n{i}. {article['code']} - {article['description']}")
    print(f"   Purchased: {article['total_quantity']} units")
    print(f"   Revenue: ${article['total_value']:.2f}")

print("\n" + "=" * 60)
print("RECENT PURCHASES")
print("=" * 60)

# Show recent purchases
purchases = shop.db.table("purchases").list()
print(f"\nShowing first 5 of {purchases['count']} purchases:")
for p in purchases["purchases"][:5]:
    print(f"\n• {p['code']} - {p['description']}")
    print(f"  Quantity: {p['quantity']} @ ${p['unit_price']:.2f} = ${p['total']:.2f}")
    print(f"  Date: {p['purchase_date']}")

print("\n" + "=" * 60)
