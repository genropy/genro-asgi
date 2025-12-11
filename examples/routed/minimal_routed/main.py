#!/usr/bin/env python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Minimal example: AsgiServer with router mode.

Demonstrates AsgiServer as a RoutedClass with built-in test endpoints.

Run with:
    python main.py
    python main.py --port 9000

Test endpoints:
    curl http://127.0.0.1:8000/test1
    curl http://127.0.0.1:8000/test2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from genro_asgi import AsgiServer


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal routed server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Server host")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Server port")
    args = parser.parse_args()

    print("Minimal Routed Server")
    print()

    # Create server with router mode
    server = AsgiServer(use_router=True)

    # Show router info
    print(f"Router: {server.router}")
    print(f"Router name: {server.router.name}")
    print()

    # Show available endpoints
    print("Endpoints:")
    print("  /test1 -> test1()")
    print("  /test2 -> test2()")
    print()

    # Run server
    print(f"Server: http://{args.host}:{args.port}")
    print()

    try:
        server.run(host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nShutdown.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
