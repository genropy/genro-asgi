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

"""Contract tests for the profile words a recipe writes on the spa front.

Design step 7: ``profiles_path``, ``profile_name`` and ``orchestration_control``
are attributes of the APPLICATION element of the spa app — the envelope the site
dialect owns and leaves open for an app's own constructor kwargs — and never
words of ``commander``. ``env_settings`` is not a grammar word at all: it is a
dict a Python recipe builds at runtime and hands over as a plain kwarg.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from genro_asgi import AsgiServer
from genro_asgi.applications.spa_app import ORCHESTRATION_ROOT, SpaApplication
from genro_asgi.config.builder import AsgiConfigBuilder
from genro_asgi.config.handler import ConfigurationHandler
from genro_asgi.spa.orchestration import SpaCommander


class QuietCommander(SpaCommander):
    """The real vertex, minus the processes: nothing is launched, nothing forked."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class GrammarFront(SpaApplication):
    """The front under test, with a pool that costs nothing to build."""

    commander_class = QuietCommander


def recipe_with(root: Path, **front_words: Any) -> type[AsgiConfigBuilder]:
    """A recipe writing ``front_words`` on the application element of the front."""

    class GrammarConfig(AsgiConfigBuilder):
        def main(self, configuration_root: Any) -> None:
            cfg = configuration_root.configuration()
            applications = cfg.applications()
            front = applications.application(
                code="site0", mount="", app_class=GrammarFront, **front_words
            )
            commander = front.commander(
                frozen_users_path=str(root / "frozen_users"),
                instance_dir=str(root / "i"),
            )
            commander.groups(default="standard").group(
                name="standard", entry_module="never.launched"
            )

    return GrammarConfig


def commander_recipe_with(root: Path, **commander_words: Any) -> type[AsgiConfigBuilder]:
    """The same recipe, with the words written on ``commander`` instead."""

    class CommanderConfig(AsgiConfigBuilder):
        def main(self, configuration_root: Any) -> None:
            cfg = configuration_root.configuration()
            applications = cfg.applications()
            front = applications.application(code="site0", mount="", app_class=GrammarFront)
            commander = front.commander(
                frozen_users_path=str(root / "frozen_users"),
                instance_dir=str(root / "i"),
                **commander_words,
            )
            commander.groups(default="standard").group(
                name="standard", entry_module="never.launched"
            )

    return CommanderConfig


def test_application_element_accepts_profile_words(tmp_path: Path) -> None:
    # wf:contract: a recipe writes profiles_path, profile_name and
    # wf:contract: orchestration_control on the APPLICATION element of the spa
    # wf:contract: app and they reach the SpaApplication kwargs; they are NOT
    # wf:contract: words of the commander element.
    profiles = tmp_path / "profiles"
    recipe = recipe_with(
        tmp_path,
        profiles_path=str(profiles),
        profile_name="busy_hours",
        orchestration_control=True,
    )

    entries, _default = ConfigurationHandler(recipe).applications()
    app_class, app_kwargs = entries[0]
    assert app_class is GrammarFront
    assert app_kwargs["profiles_path"] == str(profiles)
    assert app_kwargs["profile_name"] == "busy_hours"
    assert app_kwargs["orchestration_control"] is True

    front = AsgiServer(config=recipe).applications["site0"]
    assert front.profiles_path == str(profiles)
    assert front.profile_name == "busy_hours"
    assert front.orchestration_control is True
    assert ORCHESTRATION_ROOT in front.internal_roots

    # The commander element is closed: the same words are refused there.
    for word in ("profiles_path", "profile_name", "orchestration_control"):
        with pytest.raises(Exception) as refusal:
            ConfigurationHandler(commander_recipe_with(tmp_path, **{word: "x"})).applications()
        assert word in str(refusal.value)


def test_env_settings_is_not_grammar(tmp_path: Path) -> None:
    # wf:contract: env_settings is not writable from the grammar: it stays a
    # wf:contract: runtime dict passed by the Python recipe.
    grammar_file = tmp_path / "site_grammar.json"
    AsgiConfigBuilder.to_grammar(str(grammar_file))
    document = json.dumps(json.load(grammar_file.open()))
    assert "env_settings" not in document

    with pytest.raises(Exception) as refusal:
        ConfigurationHandler(
            commander_recipe_with(tmp_path, env_settings={"worker_max_users": 3})
        ).applications()
    assert "env_settings" in str(refusal.value)

    front = GrammarFront(code="site0", mount="", env_settings={"worker_max_users": 3})
    assert front.env_settings == {"worker_max_users": 3}
