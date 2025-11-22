"""Basic tests for genro-asgi.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

import genro_asgi


def test_version() -> None:
    """Test that version is defined."""
    assert genro_asgi.__version__ == "0.1.0"


def test_exports() -> None:
    """Test that main exports are available."""
    assert hasattr(genro_asgi, "Application")
    assert hasattr(genro_asgi, "Request")
    assert hasattr(genro_asgi, "Response")
    assert hasattr(genro_asgi, "JSONResponse")
    assert hasattr(genro_asgi, "HTMLResponse")
    assert hasattr(genro_asgi, "PlainTextResponse")
    assert hasattr(genro_asgi, "Lifespan")
