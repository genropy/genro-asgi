Server application
==================

The ``genro_asgi_server_app`` package: the system surface a server exposes under
``/_server``, shipped by the same distribution as the core and imported by none
of it. It is declared like any other application, with the code ``_server``::

    from genro_asgi import AsgiServer
    from genro_asgi_server_app import ServerApplication

    server = AsgiServer(applications=[ServerApplication(), MyApp(mount="")])

A server that declares none exposes no ``/_server/...``. The management pages
themselves are not here: this package serves the JSON a page drives.

Application and grammar
-----------------------

.. autoclass:: genro_asgi_server_app.server_app.ServerApplication
   :members: login_policy, oidc_providers, sections, auth_section, attach_section,
             register_auth_method, read_declared_login_surface

.. autoclass:: genro_asgi_server_app.server_app.ServerApplicationGrammar
   :members: login, oidc, provider

Login methods
-------------

.. automodule:: genro_asgi_server_app.auth_method
   :members:
   :show-inheritance:

.. automodule:: genro_asgi_server_app.oidc_method
   :members:
   :show-inheritance:

Sections
--------

.. automodule:: genro_asgi_server_app.server_sections.auth_section
   :members:
   :show-inheritance:

.. automodule:: genro_asgi_server_app.server_sections.users_section
   :members:
   :show-inheritance:

.. automodule:: genro_asgi_server_app.server_sections.tokens_section
   :members:
   :show-inheritance:

.. automodule:: genro_asgi_server_app.server_sections.tasks_section
   :members:
   :show-inheritance:

.. automodule:: genro_asgi_server_app.server_sections.monitor_section
   :members:
   :show-inheritance:
