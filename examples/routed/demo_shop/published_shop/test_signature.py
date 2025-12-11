"""Test script to check method signature."""

import sys
import inspect
from pathlib import Path

# Setup paths like main.py does
smpub_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(smpub_root))

from examples.demo_shop.sample_shop.shop import Shop

# Create shop
db_path = Path(__file__).parent / "shop.db"
shop = Shop(f"sqlite:{db_path}")

# Get types handler
types_handler = shop.db.table("types")

# Check what we get when accessing the method
print("=== Direct method access ===")
method = getattr(types_handler, "list")
print(f"Method type: {type(method)}")
print(f"Method: {method}")
print()

# Try signature
print("=== Signature analysis ===")
try:
    sig = inspect.signature(method)
    print(f"Signature: {sig}")
    print("\nParameters:")
    for param_name, param in sig.parameters.items():
        print(f"  {param_name}:")
        print(f"    annotation: {param.annotation}")
        print(f"    default: {param.default}")
        print(f"    kind: {param.kind}")
except Exception as e:
    print(f"Error getting signature: {e}")
    import traceback

    traceback.print_exc()

# Also check the class method
print("\n=== Class method (ArticleTypes.list) ===")
from examples.demo_shop.sample_shop.tables import ArticleTypes

class_method = getattr(ArticleTypes, "list")
print(f"Class method type: {type(class_method)}")
try:
    sig2 = inspect.signature(class_method)
    print(f"Class method signature: {sig2}")
    print("\nClass method parameters:")
    for param_name, param in sig2.parameters.items():
        print(f"  {param_name}: {param.annotation}, default={param.default}")
except Exception as e:
    print(f"Error: {e}")

# Check for __wrapped__ attribute
print("\n=== Looking for original function ===")
print(f"Has __wrapped__: {hasattr(method, '__wrapped__')}")
if hasattr(method, "__wrapped__"):
    wrapped = method.__wrapped__
    print(f"__wrapped__ type: {type(wrapped)}")
    try:
        wrapped_sig = inspect.signature(wrapped)
        print(f"__wrapped__ signature: {wrapped_sig}")
    except Exception as e:
        print(f"Error: {e}")

# Check method entry in switcher
print("\n=== Switcher entry ===")
switcher = getattr(types_handler.api, "dbop", None)
print(f"Switcher type: {type(switcher)}")
print(f"Switcher name: {getattr(switcher, 'name', None)}")

# Try to get the original function from switcher internals
if switcher and hasattr(switcher, "_handlers"):
    print("Has _handlers: True")
    if "list" in switcher._handlers:
        entry = switcher._handlers["list"]
        print(f"Entry type: {type(entry)}")
        print(f"Entry attributes: {dir(entry)}")
        if hasattr(entry, "func"):
            orig_func = entry.func
            print(f"Entry.func type: {type(orig_func)}")
            try:
                orig_sig = inspect.signature(orig_func)
                print(f"Original function signature: {orig_sig}")
            except Exception as e:
                print(f"Error: {e}")
