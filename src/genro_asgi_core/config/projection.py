# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Projection — the per-role slice of one whole-site config (D15).

One config describes the ENTIRE site; every process is born with
``(config, role)`` and materializes its own slice. ``Projection`` IS that
slice: a slotted object computed from the built ``SourceBag`` tree plus the
role (plus ``app=<code>`` for the hosted roles), consumed by
``ConfigurationHandler.materialize``. The projection is PER-SECTION:

- ``root`` — the public server: every section (``server``, ``middleware``,
  ``auth``, ``storage``, ``applications``, ``databases``, ``plugins``,
  ``openapi``); every application mounted, the ``default`` one primary.
- ``worker`` — the hosted process of ONE application (``app=<code>``
  required): sees only that application (as primary, no secondaries) plus
  ``databases``, ``storage`` and ``plugins`` (D15: the transversal pieces it
  needs — storage is survival infrastructure, plugins are router behavior) —
  never the public middleware, never auth or sessions, never the public
  listener address.
- ``batch`` — the same section cut as ``worker`` with no HTTP-facing
  expectations (still an ``AsgiServer`` composition in 1a; what 1a fixes is
  WHICH SECTIONS each role sees — the orchestration semantics arrive with the
  orchestration package).

The role → visible-sections rules table lives ON THE INSTANCE — nothing at
module level. Errors are explicit: an unknown role raises ``ValueError``
naming it; a hosted role without ``app=`` raises ``TypeError``; ``root`` with
``app=`` raises ``TypeError`` (it mounts every application); a hosted role
naming an undeclared application raises ``ValueError``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["Projection"]


class Projection:
    """The (role, app) slice of a built config tree (D15, per-section)."""

    __slots__ = ("_role", "_app", "_rules", "_sections")

    def __init__(self, source: Any, role: str, app: str | None = None) -> None:
        self._rules: dict[str, frozenset[str]] = {
            "root": frozenset(
                {
                    "server",
                    "middleware",
                    "auth",
                    "storage",
                    "applications",
                    "databases",
                    "plugins",
                    "openapi",
                }
            ),
            "worker": frozenset({"applications", "databases", "storage", "plugins"}),
            "batch": frozenset({"applications", "databases", "storage", "plugins"}),
        }
        if role not in self._rules:
            declared = ", ".join(sorted(self._rules))
            raise ValueError(f"unknown config role {role!r} (declared roles: {declared})")
        if role == "root":
            if app is not None:
                raise TypeError("role 'root' takes no app= — it mounts every application")
        elif app is None:
            raise TypeError(f"role {role!r} requires app=<code> naming the hosted application")
        self._role = role
        self._app = app
        visible = self._rules[role]
        self._sections = {node.node_tag: node for node in source if node.node_tag in visible}

    @property
    def role(self) -> str:
        """The declared role this slice was computed for."""
        return self._role

    @property
    def app(self) -> str | None:
        """The hosted application code (``None`` for the root role)."""
        return self._app

    @property
    def visible_sections(self) -> frozenset[str]:
        """The section tags this role sees (the D15 per-section rules table)."""
        return self._rules[self.role]

    def section(self, name: str) -> Any:
        """The named section node, or ``None`` when absent or invisible to the role."""
        return self._sections.get(name)

    def server_attrs(self) -> dict[str, Any]:
        """The ``server`` section attributes of this slice (empty for hosted roles).

        The public listener address (``host``/``port``) belongs to the root
        process; a hosted worker/batch process never inherits it. Only the
        node's own attributes — the ``session`` child is read through its own
        seam.
        """
        node = self.section("server")
        return dict(node.fixed_attr_items()) if node is not None else {}

    def session_node(self) -> Any:
        """The ``server`` section's ``session`` child node, or ``None``.

        Server-domain: absent for hosted roles (they never see ``server``).
        """
        return self._server_child("session")

    def _server_child(self, tag: str) -> Any:
        """The named child of the ``server`` section node, or ``None``."""
        node = self.section("server")
        if node is None or node.value is None or not hasattr(node.value, "nodes"):
            return None
        return next((child for child in node.value if child.node_tag == tag), None)

    def middleware_config(self) -> dict[str, Any] | None:
        """The middleware switches of this slice.

        ``root``: the ``middleware`` section attributes, or ``None`` when the
        section is absent (the composition's own defaults apply). Hosted
        roles: every default-armed middleware explicitly OFF — ``errors``
        (``middleware_default`` ON) and the ``auth``/``session`` switches the
        mixins arm via ``setdefault`` — D15's "never the public middleware";
        an explicit ``False`` always wins over the arming.
        """
        if self.role == "root":
            node = self.section("middleware")
            return dict(node.fixed_attr_items()) if node is not None else None
        return {"errors": False, "auth": False, "session": False}

    def auth_config(self) -> dict[str, Any] | None:
        """The ``auth`` section attributes, or ``None`` when absent.

        Hosted roles never see the ``auth`` section, so this degrades to
        ``None`` for them with no special casing.
        """
        node = self.section("auth")
        return dict(node.fixed_attr_items()) if node is not None else None

    def storage_config(self) -> dict[str, Any] | None:
        """The ``storage`` mounts of this slice as ``{code: {path, encrypted}}``.

        ``None`` when the section is absent (the composition builds a default
        ``LocalStorage``). Visible to every role — storage is D15 survival
        infrastructure, not root-only like middleware/auth.
        """
        node = self.section("storage")
        if node is None:
            return None
        children = node.value
        mount_nodes = list(children) if children is not None else []
        mounts = [dict(mount_node.fixed_attr_items()) for mount_node in mount_nodes]
        return {
            attrs["code"]: {"path": attrs.get("path"), "encrypted": bool(attrs.get("encrypted"))}
            for attrs in mounts
        }

    def databases_config(self) -> dict[str, dict[str, Any]]:
        """The ``databases`` descriptors of this slice as ``{code: {db_class, db_handler_class, params}}``.

        Empty dict when the section is absent or invisible to the role.
        ``db_handler_class`` is ``None`` when the recipe omits it (the
        materializer's default applies); ``params`` are the remaining
        connection kwargs handed to ``db_class(**params)``. Visible to
        ``root``, ``worker`` and ``batch`` (D15 transversal): 1b materializes
        the whole section for every role that sees it — the per-mount slice
        arrives with orchestration.
        """
        node = self.section("databases")
        if node is None:
            return {}
        children = node.value
        db_nodes = list(children) if children is not None else []
        result: dict[str, dict[str, Any]] = {}
        for db_node in db_nodes:
            attrs = dict(db_node.fixed_attr_items())
            code = attrs.pop("code")
            db_class = attrs.pop("db_class")
            result[code] = {
                "db_class": db_class,
                "db_handler_class": attrs.pop("db_handler_class", None),
                "params": attrs,
            }
        return result

    def plugins_config(self) -> dict[str, bool | dict[str, Any]] | None:
        """The ``plugins`` switches of this slice as ``{code: bool | dict}``.

        ``None`` when the section is absent (the composition arms no extra
        plugins). Each ``plugin`` child maps to ``False`` when ``enabled`` is
        explicitly false, to its remaining options dict when it carries any,
        else to ``True``. Visible to every role — plugins are D15 transversal
        router behavior, like storage and databases.
        """
        node = self.section("plugins")
        if node is None:
            return None
        children = node.value
        plugin_nodes = list(children) if children is not None else []
        result: dict[str, bool | dict[str, Any]] = {}
        for plugin_node in plugin_nodes:
            attrs = dict(plugin_node.fixed_attr_items())
            code = attrs.pop("code")
            enabled = attrs.pop("enabled", True)
            if not enabled:
                result[code] = False
            elif attrs:
                result[code] = attrs
            else:
                result[code] = True
        return result

    def applications(self) -> tuple[Any, list[Any]]:
        """The role's application cut: ``(primary_node, secondary_nodes)``.

        ``root``: the ``default`` app (or the lone app when ``default`` is
        omitted) is the primary, every other app a secondary. Hosted roles:
        ONLY the ``app=`` application, as primary with no secondaries.
        """
        apps_node = self.section("applications")
        if apps_node is None:
            raise ValueError("config declares no applications; a primary application is required")
        children = apps_node.value
        app_nodes = list(children) if children is not None else []
        if not app_nodes:
            raise ValueError("the applications section declares no application")

        by_code = {dict(node.fixed_attr_items()).get("code"): node for node in app_nodes}
        if self.app is not None:
            if self.app not in by_code:
                raise ValueError(f"role {self.role!r} hosts undeclared application {self.app!r}")
            return by_code[self.app], []

        default_code = dict(apps_node.fixed_attr_items()).get("default")
        if default_code is not None:
            if default_code not in by_code:
                raise ValueError(
                    f"applications default {default_code!r} names no declared application"
                )
            primary_node = by_code[default_code]
        elif len(app_nodes) == 1:
            primary_node = app_nodes[0]
        else:
            raise ValueError("multiple applications but no 'default' names the primary")
        secondaries = [node for node in app_nodes if node is not primary_node]
        return primary_node, secondaries


if __name__ == "__main__":
    from genro_builders.builder import BuilderHandler

    from .builder import AsgiConfigBuilder

    class _Recipe(AsgiConfigBuilder):
        def main(self, root: Any) -> None:
            root.server(host="127.0.0.1", port=8000)
            root.middleware(cors=True)
            root.auth(basic={"admin": {"password": "secret"}})
            apps = root.applications(default="shop")
            apps.application(code="shop", app_class=object)
            apps.application(code="erp", app_class=object)

    recipe = _Recipe(name="config")
    BuilderHandler().add_builder(recipe)

    root_slice = Projection(recipe.source, role="root")
    assert root_slice.server_attrs() == {"host": "127.0.0.1", "port": 8000}
    assert root_slice.middleware_config() == {"cors": True}
    assert root_slice.auth_config() == {"basic": {"admin": {"password": "secret"}}}
    primary, secondaries = root_slice.applications()
    assert dict(primary.fixed_attr_items())["code"] == "shop"
    assert len(secondaries) == 1

    worker_slice = Projection(recipe.source, role="worker", app="erp")
    assert worker_slice.server_attrs() == {}
    assert worker_slice.auth_config() is None
    assert worker_slice.middleware_config() == {"errors": False, "auth": False, "session": False}
    primary, secondaries = worker_slice.applications()
    assert dict(primary.fixed_attr_items())["code"] == "erp"
    assert secondaries == []

    try:
        Projection(recipe.source, role="manager")
    except ValueError as error:
        assert "manager" in str(error)
    else:
        raise AssertionError("expected ValueError on unknown role")

    try:
        Projection(recipe.source, role="worker")
    except TypeError:
        pass
    else:
        raise AssertionError("expected TypeError on worker without app=")
