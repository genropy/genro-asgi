#!/usr/bin/env python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Demo server showing basic AsgiServer usage.

Run with:
    python examples/demo_server.py

Then visit:
    http://127.0.0.1:8000/api/
    http://127.0.0.1:8000/api/hello
"""

from genro_asgi import AsgiServer
from genro_asgi.types import Receive, Scope, Send


async def demo_app(scope: Scope, receive: Receive, send: Send) -> None:
    """Simple demo app that responds with Hello."""
    _ = receive  # unused in this demo

    if scope["type"] == "http":
        path = scope.get("path", "/")
        body = f"Hello from AsgiServer! Path: {path}".encode()

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


if __name__ == "__main__":
    server = AsgiServer(config={"host": "127.0.0.1", "port": 8000})
    server.mount("/api", demo_app)
    server.run()
