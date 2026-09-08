Multiworker SPA integration
===========================

These are integration surfaces of the separate ``genro_asgi_multiworker_spa``
package. See :doc:`../guides/multiworker-spa` before configuring a pool.

Front and worker
----------------

.. autoclass:: genro_asgi_multiworker_spa.spa_app.SpaApplication
   :members: commander, handshake_cookie

.. autoclass:: genro_asgi_multiworker_spa.orchestration.spa_worker.SpaWorker
   :members: hosted_app_seam, global_store, send_message, run_sync, build_request_slot, on_request_served

Hosted application adapters
---------------------------

.. automodule:: genro_asgi_multiworker_spa.environ
   :members: AsgiSeam, WsgiSeam

Global store
------------

.. autoclass:: genro_asgi_multiworker_spa.global_store.GlobalStoreClient
   :members: get, set, delete, for_update

.. autoclass:: genro_asgi_multiworker_spa.global_store.GlobalStoreLease
   :members: abort

.. autoexception:: genro_asgi_multiworker_spa.global_store.GlobalStoreCommitUnconfirmed
