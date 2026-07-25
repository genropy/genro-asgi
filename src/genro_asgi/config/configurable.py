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

"""Configurable classes — per-class configuration grammars (extraction-ready).

The configuration grammar follows the class hierarchy: every runtime class
can declare its own grammar as a *companion* mixin of ``@element`` markers,
linked through the ``config_grammar`` class attribute::

    class VehicleElements:
        @element(sub_tags="")
        def wheels(self) -> None:
            '''Wheel options.'''

    class Vehicle:
        config_grammar = VehicleElements

Companions mirror the runtime hierarchy with plain Python inheritance
(``CarElements(VehicleElements)`` as ``Car(Vehicle)``), so grammars compose
along the chain exactly like D16 cooperative constructors — an element
declared by class X materializes into the kwarg class X peels. The site
recipe composes companions EXPLICITLY
(``class Site(BuilderBase, Car.config_grammar)``): no auto-discovery, no
global registry. genro-builders collects the markers from mixin bases
without removing them (``_pop_decorated_methods``), so a companion stays
introspectable after any number of recipes consumed it.

The module offers three operations over that convention:

- :func:`declared_elements` — which tags a companion chain declares
  (MRO scan of the ``_decorator`` markers).
- :func:`element_kwargs` — the materializer: a node's attributes become
  constructor kwargs, each child element becomes a dict-valued kwarg keyed
  by its tag (``users(mount=...)`` -> ``users={"mount": ...}``). STRICT:
  a child not declared by the owner's grammar chain, a duplicate child, or
  a child carrying children of its own raise :class:`ConfigError` — never
  a silent skip (D16 symmetry).
- :func:`resolve_pointers` — resolve a node's ``^`` pointers through the
  builder's ``runtime_values``; a configured pointer that resolves empty
  (None or "") raises :class:`ConfigError` (a secret the recipe promised
  MUST exist — no silent degradation).

EXTRACTION BOUNDARY: this module imports nothing from genro_asgi and
nothing ASGI — it is duck-typed over genro-builders' public seams (the
``_decorator`` marker attribute, the source-node API, ``runtime_values``)
and moves as-is to genro-builders or a standalone package, tests included.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ConfigError", "declared_elements", "element_kwargs", "resolve_pointers"]


class ConfigError(Exception):
    """A configuration recipe names something its grammar chain cannot honor."""


def declared_elements(grammar: type) -> set[str]:
    """Return the tags declared by ``grammar``'s companion chain.

    Walks the companion's MRO collecting every attribute that carries a
    ``_decorator`` marker; ``@abstract`` declarations (inheritance-only)
    and ``@container`` methods (source generators, not tags) are skipped —
    the same filter genro-builders applies when it builds a class schema.
    """
    tags: set[str] = set()
    for klass in grammar.__mro__:
        for name, obj in vars(klass).items():
            decorator = getattr(obj, "_decorator", None)
            if decorator is None:
                continue
            if decorator.get("abstract") or decorator.get("container"):
                continue
            tags.add(name)
    return tags


def element_kwargs(
    node: Any, owner_class: type, exclude: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Materialize ``node`` into constructor kwargs for ``owner_class``.

    The node's attributes become kwargs (minus ``exclude``, the names the
    caller consumes itself); each child element becomes a dict-valued kwarg
    keyed by its tag. Strict-unknown: a child whose tag is not declared by
    ``owner_class.config_grammar``'s chain (or any child when the owner has
    no ``config_grammar``) raises :class:`ConfigError`, as do a duplicate
    child tag and a child carrying children of its own (the materializer
    maps ONE level: child -> dict kwarg).
    """
    kwargs: dict[str, Any] = {
        name: value for name, value in node.fixed_attr_items() if name not in exclude
    }
    children = node.value
    if children is None or not hasattr(children, "nodes"):
        return kwargs
    grammar = getattr(owner_class, "config_grammar", None)
    declared = declared_elements(grammar) if grammar is not None else set()
    for child in children:
        tag = child.node_tag
        if tag not in declared:
            raise ConfigError(
                f"config element {node.node_tag!r}: child {tag!r} is not "
                f"declared by the config grammar of {owner_class.__name__}"
            )
        if tag in kwargs:
            raise ConfigError(
                f"config element {node.node_tag!r}: child {tag!r} already "
                "materialized (duplicate child or attribute collision)"
            )
        grandchildren = child.value
        if grandchildren is not None and hasattr(grandchildren, "nodes"):
            raise ConfigError(
                f"config element {node.node_tag!r}: child {tag!r} carries "
                "nested children; the materializer maps one level "
                "(child -> dict kwarg)"
            )
        kwargs[tag] = dict(child.fixed_attr_items())
    return kwargs


def resolve_pointers(builder: Any, node: Any) -> tuple[Any, dict[str, Any]]:
    """Resolve ``node``'s ``^`` pointers via ``builder.runtime_values``, strictly.

    Returns the ``(runtime_value, runtime_attrs)`` pair unchanged, after
    enforcing the boot rule: a configured ``^`` pointer (attribute or node
    value) that resolves empty — None or "" — raises :class:`ConfigError`
    naming the subject and the pointer. Non-pointer attributes pass through
    untouched.
    """
    value, attrs = builder.runtime_values(node)
    for attrname, raw in node.runtime_to_evaluate().items():
        if node.pointer_type(raw) != "^":
            continue
        resolved = value if attrname is None else attrs.get(attrname)
        if resolved is None or resolved == "":
            subject = "value" if attrname is None else f"attribute {attrname!r}"
            raise ConfigError(
                f"config element {node.node_tag!r}: {subject} pointer "
                f"{raw!r} resolved empty"
            )
    return value, attrs
