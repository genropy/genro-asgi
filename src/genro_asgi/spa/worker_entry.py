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

"""The worker process entry point: one child, one channel, nothing else.

``python -m genro_asgi.spa.worker_entry`` is what the commander spawns. The
child is **monolingual**: it speaks only the channel — no HTTP port, no
uvicorn, no fallback door. Its whole configuration arrives in the
``GENRO_ASGI_WORKER`` environment variable as one JSON object::

    {"name": "W:w1",
     "address": "uds:/tmp/gnrhub_x/hub.sock",
     "worker_class": "genro_asgi.spa.worker:UserStickyWorker",
     "kwargs": {"max_threads": 8}}

``name`` and ``address`` are mandatory (the commander always knows both);
``worker_class`` is a ``module.path:ClassName`` dotted reference defaulting to
:class:`~genro_asgi.spa.worker.UserStickyWorker`, and ``kwargs`` reaches that
class's constructor. A missing or malformed variable is a spawn contract
violation: the process exits with a message, never with a guessed default.

The life is one ``asyncio.run``: build the worker, present it on the hub
(REGISTER carries the typed name), start its sender and heartbeat, then wait
on the channel. That wait ends by itself in both deaths — the hub going away
(EOF → orphan) and a deliberate SIGTERM, which closes the channel from this
side so no orphan is ever reported for a requested stop. Either way the
teardown is the same and the exit code is 0: the commander reads a clean exit
as "this child is gone", not as a crash to throttle.

``WorkerEntry`` is importable and testable on its own — the argparse-free
class does the work and the ``main()`` at the bottom is the thin ``python -m``
shell around it.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import signal
import sys
from typing import Any

from .worker import UserStickyWorker, WorkerChannelClient

__all__ = ["WorkerEntry"]


class WorkerEntry:
    """One spawned worker's whole life, driven by the ``GENRO_ASGI_WORKER`` payload."""

    ENV_VAR = "GENRO_ASGI_WORKER"
    DEFAULT_WORKER_CLASS = "genro_asgi.spa.worker:UserStickyWorker"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Args:
        config: the spawn payload; read from the environment when omitted.
        """
        self.logger = logging.getLogger(__name__)
        self.config = self.read_config() if config is None else config
        self.name: str = self.config["name"]
        self.address: str = self.config["address"]
        self.worker_class: str = self.config.get("worker_class") or self.DEFAULT_WORKER_CLASS
        self.kwargs: dict[str, Any] = self.config.get("kwargs") or {}
        self.worker: UserStickyWorker | None = None
        self.client: WorkerChannelClient | None = None

    def read_config(self) -> dict[str, Any]:
        """Parse and validate the spawn payload; a violation ends the process."""
        raw = os.environ.get(self.ENV_VAR)
        if not raw:
            raise SystemExit(f"{self.ENV_VAR} is not set: nothing to spawn")
        try:
            config = json.loads(raw)
        except ValueError as exc:
            raise SystemExit(f"{self.ENV_VAR} is not valid JSON: {exc}") from None
        if not isinstance(config, dict):
            raise SystemExit(f"{self.ENV_VAR} must be a JSON object, got {type(config).__name__}")
        missing = [key for key in ("name", "address") if not config.get(key)]
        if missing:
            raise SystemExit(f"{self.ENV_VAR} is missing {', '.join(missing)}")
        return config

    def load_class(self, dotted: str) -> type:
        """Resolve a ``module.path:ClassName`` dotted reference to the class object."""
        module_path, _, class_name = dotted.partition(":")
        if not module_path or not class_name:
            raise SystemExit(f"worker_class must be 'module.path:ClassName', got {dotted!r}")
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def build_worker(self) -> UserStickyWorker:
        """Instantiate the configured worker class with its own kwargs."""
        worker_class = self.load_class(self.worker_class)
        return worker_class(self.name, **self.kwargs)

    def request_stop(self) -> None:
        """SIGTERM: close the channel from this side — a stop is not an orphan."""
        self.logger.info("%s: stop requested", self.name)
        asyncio.get_running_loop().create_task(self.client.close())

    async def serve(self) -> None:
        """Present on the hub, run, and wait for whichever death comes first."""
        self.worker = self.build_worker()
        self.client = WorkerChannelClient(self.address, self.name)
        self.worker.attach_channel(self.client)
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, self.request_stop)
        await self.client.connect()
        await self.worker.start()
        self.logger.info("%s: serving on %s (pid %s)", self.name, self.address, os.getpid())
        await self.client.wait_closed()
        await self.worker.shutdown()
        self.logger.info("%s: exited cleanly", self.name)

    def run(self) -> int:
        """Run the whole life; 0 on either clean death."""
        asyncio.run(self.serve())
        return 0


def main() -> int:
    """``python -m genro_asgi.spa.worker_entry``: the spawn shell."""
    logging.basicConfig(level=os.environ.get("GENRO_ASGI_LOG_LEVEL", "INFO"))
    return WorkerEntry().run()


if __name__ == "__main__":
    sys.exit(main())
