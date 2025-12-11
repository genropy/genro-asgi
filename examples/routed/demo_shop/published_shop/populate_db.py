#!/usr/bin/env python3
"""Populate the published_shop database."""

import sys
from pathlib import Path

# Add repo paths (smartpublisher/src and examples/)
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root))

from examples.demo_shop.sample_shop.shop import Shop

db_path = Path(__file__).parent / "shop.db"

# Start from a clean slate to avoid unique/foreign-key conflicts
if db_path.exists():
    db_path.unlink()

shop = Shop(f"sqlite:{db_path}")
result = shop.populateDb()
print(f"Database populated: {result}")
