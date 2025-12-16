"""DbopPlugin - Database operations plugin for genro_routes."""

from __future__ import annotations

from typing import Any, Callable

from genro_routes import Router
from genro_routes.plugins._base_plugin import BasePlugin, MethodEntry


class DbopPlugin(BasePlugin):
    """Database cursor injection and transaction management."""

    plugin_code = "dbop"
    plugin_description = "Inject cursor, commit on success, rollback on exception"

    def wrap_handler(
        self, router: Router, entry: MethodEntry, call_next: Callable
    ) -> Callable:
        """Inject cursor, commit on success, rollback on exception."""

        def wrapper(*args: Any, **kwargs: Any) -> Any:
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
                    pass
                raise

        return wrapper


Router.register_plugin(DbopPlugin)
