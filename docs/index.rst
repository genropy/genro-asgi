Genro ASGI Documentation
========================

**Genro ASGI** is a minimal, stable ASGI foundation - a framework-agnostic toolkit for building high-performance web services.

Overview
--------

Genro ASGI provides essential components for ASGI applications:

- Core ASGI server with routing via genro_routes
- Request/Response utilities
- Lifespan management
- Essential middleware (CORS, errors, compression, logging)
- Static file serving via StaticSite application
- WebSocket extension protocol (WSX)
- Zero external dependencies (stdlib only, optional orjson)

Features
--------

* **Zero Dependencies**: Built entirely on Python stdlib
* **Framework-Agnostic**: Use as foundation or integrate with existing frameworks
* **Production-Ready**: Minimal, tested, and stable
* **Type-Safe**: Full type hints for better IDE support
* **Router Integration**: Uses genro_routes for flexible routing
* **Static Files**: Built-in StaticSite application for serving static content

Installation
------------

.. code-block:: bash

   # Basic installation
   pip install genro-asgi

   # With fast JSON support
   pip install genro-asgi[json]

Quick Start
-----------

**CLI - Serve a static site:**

.. code-block:: bash

   # Create config.yaml
   cat > config.yaml << EOF
   server:
     host: "127.0.0.1"
     port: 8000

   apps:
     static:
       module: "genro_asgi:StaticSite"
       directory: "./public"
       index: "index.html"
   EOF

   # Run server
   python -m genro_asgi serve .

**Python - Custom server:**

.. code-block:: python

   from genro_asgi import AsgiServer, JSONResponse
   from genro_routes import route

   class MyServer(AsgiServer):
       @route("api/hello")
       def hello(self, request):
           return JSONResponse({"message": "Hello!"})

   if __name__ == "__main__":
       server = MyServer()
       server.run()

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Architecture

   architecture/00-overview
   architecture/01-server
   architecture/02-request-system
   architecture/03-response-system
   architecture/04-executors
   architecture/05-lifespan
   architecture/06-wsx-protocol
   architecture/07-streaming

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/index

License
-------

Copyright 2025 Softwell S.r.l.

Licensed under the Apache License, Version 2.0.

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
