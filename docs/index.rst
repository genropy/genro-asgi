Genro ASGI Documentation
========================

**Genro ASGI** is a minimal, stable ASGI foundation - a framework-agnostic toolkit for building high-performance web services.

Overview
--------

Genro ASGI provides essential components for ASGI applications:

- Core ASGI application
- Request/Response utilities
- Lifespan management
- Essential middleware (CORS, errors, compression, static files)
- Zero external dependencies (stdlib only)

Features
--------

* **Zero Dependencies**: Built entirely on Python stdlib
* **Framework-Agnostic**: Use as foundation or integrate with existing frameworks
* **Production-Ready**: Minimal, tested, and stable
* **Type-Safe**: Full type hints for better IDE support

Installation
------------

.. code-block:: bash

   # Basic installation (stdlib only)
   pip install genro-asgi

   # With fast JSON support
   pip install genro-asgi[json]

Quick Start
-----------

.. code-block:: python

   from genro_asgi import Application, JSONResponse

   app = Application()

   async def handler(scope, receive, send):
       response = JSONResponse({"message": "Hello from Genro ASGI"})
       await response.send(send)

API Reference
-------------

.. toctree::
   :maxdepth: 2

   api/application
   api/request
   api/response
   api/lifespan
   api/middleware

License
-------

Copyright 2025 Softwell S.r.l.

Licensed under the Apache License, Version 2.0.

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
