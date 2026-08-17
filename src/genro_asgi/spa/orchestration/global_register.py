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

"""GlobalRegister: the master of the store every worker holds a replica of.

One object, on the Commander, and it is the only writer of that content. A
worker reads its own replica and never writes it: what it wants written travels
up, is written here, and comes back down as the whole content again.

**Whole copies, always.** There is no delta on the wire and no version number on
the wire either: the replica is REPLACED entire, at the presentation like at
every later change. So a newborn is not a special case, nothing can arrive out of
order, and a worker that missed a change is indistinguishable from one that was
just born. It costs the whole store per change, which at this scale is nothing —
kilobytes, changing something like once every three hours.

**The content is a Bag, and it goes on the wire TYTX-encoded.** The encoding is
where the store meets the channel; the Bag is where it meets the application. A
reader on this side holds the Bag itself, so a change is visible to it without
anything being shipped.

The read-modify-write grant — one worker at a time holding the master while it
computes a new value — is the lock, and it arrives with the request chain.
"""

from __future__ import annotations

from typing import Any

from genro_bag import Bag
from genro_tytx import to_tytx

__all__ = ["GlobalRegister"]


class GlobalRegister:
    """The global store's master: a Bag, and the form it travels in."""

    def __init__(self) -> None:
        #: The content itself. Whoever reads it here reads the master.
        self.bag = Bag()

    @property
    def item_tytx(self) -> str | bytes:
        """The whole content in the form it travels in, ready for an envelope.

        Returns:
            The TYTX-encoded store — whole, because that is the only form a
            replica is ever replaced with. The json transport encodes to a
            string; the type is the encoder's own promise, and this side never
            looks inside it anyway.
        """
        return to_tytx(self.bag, "json")

    def set_item(self, path: str, value: Any) -> None:
        """Write one path of the master.

        Args:
            path: the Bag path to write.
            value: what to write there.

        Acts on the content. Telling the replicas is the Commander's business,
        and it is not built: a change reaches a process that is already alive
        only once the update is sent to everybody.
        """
        self.bag.set_item(path, value)

    def drop_item(self, path: str) -> None:
        """Remove one path of the master.

        Args:
            path: the Bag path to remove; one that is not there is that same
                outcome.

        Acts on the content, exactly as a write does.
        """
        self.bag.pop(path)
