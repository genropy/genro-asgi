genro-asgi documentation
========================

**genro-asgi** is a minimal ASGI server core: one instance-isolated server that
mounts your applications, routes requests through `genro-routes
<https://pypi.org/project/genro-routes/>`_, and grows authentication, sessions,
background tasks, OpenAPI and MCP by composition. No globals, no module state —
the server is an object you build, run, and throw away.

New here? Start with :doc:`getting-started`. Coming from another ASGI framework?
Read :doc:`coming-from-fastapi`.

.. toctree::
   :maxdepth: 2
   :caption: Getting started

   getting-started
   concepts
   coming-from-fastapi

.. toctree::
   :maxdepth: 2
   :caption: Guides

   guides/index

.. toctree::
   :maxdepth: 2
   :caption: Architecture

   architecture/overview

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/index

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
