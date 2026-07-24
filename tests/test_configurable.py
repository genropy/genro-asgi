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

"""Configurable-classes mechanism tests (Macro 5b wave 1 Phase 8).

Exercises ``config/configurable.py`` over a FICTIONAL class hierarchy —
deliberately ASGI-free, because the module is extraction-ready and these
tests migrate with it: ``Vehicle``/``Car`` runtime classes linked to
``VehicleElements``/``CarElements`` companions via ``config_grammar``, and
recipes composing the companions EXPLICITLY on ``BuilderBase``.
"""

from __future__ import annotations

from typing import Any

import pytest
from genro_bag.resolvers import EnvResolver
from genro_builders.builder import BuilderBase, BuilderHandler, abstract, container, element

from genro_asgi.config.configurable import (
    ConfigError,
    declared_elements,
    element_kwargs,
    resolve_pointers,
)

VAULT_ENV_VAR = "GENRO_TEST_VAULT_PASSWORD"


class VehicleElements:
    """Companion grammar of ``Vehicle``."""

    @element(sub_tags="")
    def wheels(self) -> None:
        """Wheel options."""

    @abstract(sub_tags="")
    def running_gear(self) -> None:
        """Abstract: inheritance-only, never a tag."""


class CarElements(VehicleElements):
    """Companion grammar of ``Car`` — inherits ``wheels``, adds ``engine``."""

    @element(sub_tags="")
    def engine(self) -> None:
        """Engine options."""

    @container
    def preset(self, node: Any) -> Any:
        """Container: generates source at call time, never a tag."""
        return node


class BoatElements:
    """Foreign grammar: ``anchor`` is NOT part of the Car chain."""

    @element(sub_tags="")
    def anchor(self) -> None:
        """Anchor options."""


class SiteElements:
    """Root elements of the fictional site recipe."""

    @element(sub_tags="*")
    def car(self) -> None:
        """One car: attributes plus children from Car's grammar."""

    @element(sub_tags="*", parent_tags="car")
    def rack(self) -> None:
        """A car child that may carry children of its own."""


class Vehicle:
    """Runtime base class: declares the base grammar."""

    config_grammar = VehicleElements


class Car(Vehicle):
    """Runtime subclass: its companion extends the base one."""

    config_grammar = CarElements


class Bare:
    """Runtime class with NO config_grammar: declares no children."""


class SiteRecipe(BuilderBase, SiteElements, CarElements):
    """A car with attributes and both declared children."""

    def main(self, root: Any) -> None:
        car = root.car(color="red", doors=5)
        car.wheels(count=4, size=17)
        car.engine(cc=1600)


class ForeignChildRecipe(BuilderBase, SiteElements, CarElements, BoatElements):
    """Build-legal (car allows any tag) but ``anchor`` is not Car grammar."""

    def main(self, root: Any) -> None:
        car = root.car(color="blue")
        car.anchor(weight=10)


class DuplicateChildRecipe(BuilderBase, SiteElements, CarElements):
    """Two ``wheels`` children under the same car."""

    def main(self, root: Any) -> None:
        car = root.car(color="green")
        car.wheels(count=4)
        car.wheels(count=6)


class NestedChildRecipe(BuilderBase, SiteElements, CarElements):
    """A ``rack`` child that carries a grandchild."""

    def main(self, root: Any) -> None:
        car = root.car(color="black")
        rack = car.rack(rails=2)
        rack.wheels(count=2)


class RackCarElements(CarElements):
    """Companion declaring ``rack`` so NestedChildRecipe fails on depth, not tag."""

    @element(sub_tags="*", parent_tags="car")
    def rack(self) -> None:
        """Same tag as SiteElements.rack, declared by this chain too."""


class RackCar(Car):
    """Runtime class whose grammar declares ``rack``."""

    config_grammar = RackCarElements


class SecretElements:
    """Grammar of the pointer recipes."""

    @element(sub_tags="")
    def vault(self) -> None:
        """Vault: secrets arrive as ``^`` pointers."""


class SecretRecipe(BuilderBase, SecretElements):
    """A vault whose password is a ``^pointer`` to an EnvResolver."""

    def setup(self, data: Any) -> None:
        data["password"] = EnvResolver(VAULT_ENV_VAR)

    def main(self, root: Any) -> None:
        root.vault(password="^password", label="main")


class SecretValueRecipe(BuilderBase, SecretElements):
    """A vault whose node VALUE is a ``^pointer``."""

    def setup(self, data: Any) -> None:
        data["body"] = EnvResolver(VAULT_ENV_VAR)

    def main(self, root: Any) -> None:
        root.vault("^body")


def build(recipe_class: type) -> Any:
    """Run a recipe: construct the builder and mount it on a fresh handler."""
    builder = recipe_class(name="config")
    BuilderHandler().add_builder(builder)
    return builder


def first_node(builder: Any) -> Any:
    """The first (root-level) node of the built source."""
    return next(iter(builder.source))


# ---------------------------------------------------------------------------
# declared_elements
# ---------------------------------------------------------------------------


def test_declared_elements_base_chain():
    assert declared_elements(VehicleElements) == {"wheels"}


def test_declared_elements_composes_by_inheritance():
    assert declared_elements(CarElements) == {"wheels", "engine"}


def test_declared_elements_skips_abstract_and_container():
    tags = declared_elements(CarElements)
    assert "running_gear" not in tags
    assert "preset" not in tags


def test_declared_elements_survives_recipe_consumption():
    build(SiteRecipe)
    assert declared_elements(CarElements) == {"wheels", "engine"}


# ---------------------------------------------------------------------------
# element_kwargs
# ---------------------------------------------------------------------------


def test_element_kwargs_attrs_and_children():
    car_node = first_node(build(SiteRecipe))
    assert element_kwargs(car_node, Car) == {
        "color": "red",
        "doors": 5,
        "wheels": {"count": 4, "size": 17},
        "engine": {"cc": 1600},
    }


def test_element_kwargs_exclude_is_honored():
    car_node = first_node(build(SiteRecipe))
    kwargs = element_kwargs(car_node, Car, exclude=("color", "doors"))
    assert "color" not in kwargs
    assert "doors" not in kwargs
    assert kwargs["wheels"] == {"count": 4, "size": 17}


def test_element_kwargs_base_grammar_rejects_subclass_child():
    car_node = first_node(build(SiteRecipe))
    with pytest.raises(ConfigError, match="'engine' is not declared"):
        element_kwargs(car_node, Vehicle)


def test_element_kwargs_undeclared_child_is_error():
    car_node = first_node(build(ForeignChildRecipe))
    with pytest.raises(ConfigError, match="'anchor' is not declared"):
        element_kwargs(car_node, Car)


def test_element_kwargs_owner_without_grammar_rejects_children():
    car_node = first_node(build(SiteRecipe))
    with pytest.raises(ConfigError, match="not declared by the config grammar of Bare"):
        element_kwargs(car_node, Bare)


def test_element_kwargs_owner_without_grammar_flat_node_ok():
    car_node = first_node(build(ForeignChildRecipe))
    anchor_node = next(iter(car_node.value))
    assert element_kwargs(anchor_node, Bare) == {"weight": 10}


def test_element_kwargs_duplicate_child_is_error():
    car_node = first_node(build(DuplicateChildRecipe))
    with pytest.raises(ConfigError, match="'wheels' already materialized"):
        element_kwargs(car_node, Car)


def test_element_kwargs_nested_grandchildren_is_error():
    car_node = first_node(build(NestedChildRecipe))
    with pytest.raises(ConfigError, match="'rack' carries nested children"):
        element_kwargs(car_node, RackCar)


# ---------------------------------------------------------------------------
# resolve_pointers
# ---------------------------------------------------------------------------


def test_resolve_pointers_resolves_and_keeps_plain_attrs(monkeypatch):
    monkeypatch.setenv(VAULT_ENV_VAR, "s3cret")
    builder = build(SecretRecipe)
    _value, attrs = resolve_pointers(builder, first_node(builder))
    assert attrs["password"] == "s3cret"
    assert attrs["label"] == "main"


def test_resolve_pointers_unset_pointer_is_error(monkeypatch):
    monkeypatch.delenv(VAULT_ENV_VAR, raising=False)
    builder = build(SecretRecipe)
    with pytest.raises(ConfigError, match="'password' pointer '\\^password' resolved empty"):
        resolve_pointers(builder, first_node(builder))


def test_resolve_pointers_empty_string_pointer_is_error(monkeypatch):
    monkeypatch.setenv(VAULT_ENV_VAR, "")
    builder = build(SecretRecipe)
    with pytest.raises(ConfigError, match="resolved empty"):
        resolve_pointers(builder, first_node(builder))


def test_resolve_pointers_value_pointer_resolves(monkeypatch):
    monkeypatch.setenv(VAULT_ENV_VAR, "payload")
    builder = build(SecretValueRecipe)
    value, _attrs = resolve_pointers(builder, first_node(builder))
    assert value == "payload"


def test_resolve_pointers_empty_value_pointer_is_error(monkeypatch):
    monkeypatch.delenv(VAULT_ENV_VAR, raising=False)
    builder = build(SecretValueRecipe)
    with pytest.raises(ConfigError, match="value pointer '\\^body' resolved empty"):
        resolve_pointers(builder, first_node(builder))
