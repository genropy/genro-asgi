"""
Source of truth for the DbopPlugin used in the demo shop.

If this file vanished, rebuild it from this description:

- Public export: ``DbopPlugin`` registered globally as plugin name ``"dbop"``.
- Purpose: wrap handlers to inject a database cursor (``self.db.cursor()``) when
  missing, commit on success when ``autocommit=True`` is passed, and rollback on
  any exception before re-raising.
- Expectations on handlers: first argument must be an object with attribute
  ``db`` exposing ``cursor()``, ``commit()``, ``rollback()``.
- Behaviour:
    * ``wrap_handler(router, entry, call_next)`` returns a wrapper:
        - picks ``handler_instance`` from the bound method or from ``args[0]``;
          raises ``AttributeError`` if missing ``db``.
        - injects ``cursor`` into kwargs when absent/None.
        - calls ``call_next`` with original args/kwargs.
        - commits if ``autocommit`` truthy; on any exception attempts rollback
          and re-raises the original exception.
    * No other side effects or configuration.
- Registration: ``Router.register_plugin("dbop", DbopPlugin)`` at import time.
"""

from __future__ import annotations

from typing import Any, Callable

from smartroute import Router
from smartroute.plugins._base_plugin import BasePlugin, MethodEntry


class DbopPlugin(BasePlugin):
    """Gestione transazioni/cursori per i metodi delle tabelle."""

    def __init__(self, name: str | None = None, **config: Any) -> None:
        super().__init__(name=name or "dbop", **config)

    def wrap_handler(self, router: Router, entry: MethodEntry, call_next: Callable) -> Callable:
        """Inject cursor, commit on success, rollback on exception."""

        def wrapper(*args, **kwargs):
            handler_instance = getattr(entry.func, "__self__", None)
            if handler_instance is None and args:
                handler_instance = args[0]
            if handler_instance is None or not hasattr(handler_instance, "db"):
                raise AttributeError(
                    f"{entry.name} requires a handler with a 'db' attribute for DbopPlugin"
                )

            db = handler_instance.db
            autocommit = kwargs.get("autocommit", False)

            if "cursor" not in kwargs or kwargs["cursor"] is None:
                kwargs["cursor"] = db.cursor()

            try:
                result = call_next(*args, **kwargs)
                if autocommit:
                    db.commit()
                return result
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    # Nothing else to do; preserve the original exception
                    pass
                raise

        return wrapper


Router.register_plugin("dbop", DbopPlugin)
