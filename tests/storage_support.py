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

"""The storage a store test runs on: one ``site:`` mount over a temporary directory.

``site_storage`` builds exactly the manager ``StorageMixin`` builds when
``storage=`` is omitted, only rooted at a ``tmp_path`` instead of the deployment
directory, so a store test exercises the real production shape. ``storage_key``
installs the at-rest key material the credential stores need.
"""

from __future__ import annotations

from genro_storage import StorageManager


def site_storage(base_dir: object, storage_key: str | None = None) -> StorageManager:
    """A ``StorageManager`` with the single ``site:`` mount rooted at ``base_dir``."""
    storage = StorageManager()
    storage.configure(
        [{"name": "site", "protocol": "local", "base_path": str(base_dir)}],
        storage_key=storage_key,
    )
    return storage
