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

"""The global store, readable by every process: one writer, a shared map, versions.

The store itself lives on the commander and nowhere else; writes reach it as
CALLs on the lane. What this module adds is the READ side: the commander
publishes the whole store into a memory-mapped file after every write it
applies, and every worker reads it locally — no round trip, no replica state,
no message. A read sees the last published version at the moment it reads,
which is fresher than any pushed copy can promise.

**One writer by construction.** Only the commander publishes, from its own
loop, so writes are serialized without any cross-process lock. The readers
map the file read-only: a worker cannot corrupt it, alive or dying.

**The layout** is a 16-byte header — ``seq`` and ``length``, two little-endian
u64 — followed by the TYTX/JSON encoding of the Bag. ``seq`` is a seqlock:
the writer bumps it to ODD before touching anything, writes length and body,
then bumps it to EVEN. A reader takes ``seq``, copies the body, reads ``seq``
again: same even value on both sides means the copy is whole; anything else
is a write in flight, and the reader tries again. The window is microseconds
wide and writes are rare, so a read that stays torn past its few retries is
an ERROR said out loud, never a silent stale value.

**Versions are the cache.** A reader keeps the last Bag it decoded together
with the ``seq`` it came from: an unchanged ``seq`` answers from the cache in
fractions of a microsecond, a changed one pays one decode. The Bag handed out
is the reader's own working copy: writing it changes nothing anywhere, which
is exactly what "read-only view" promises — writes go through the lane, as
ever.

**Growth** is the writer's ``ftruncate``: the file is sized in 4 KiB steps and
a reader that finds the header naming more bytes than it mapped simply maps
the file again.
"""

from __future__ import annotations

import mmap
import os
import struct
import threading
import time
from pathlib import Path

from genro_bag import Bag
from genro_tytx import from_tytx, to_tytx

#: Header: ``seq`` (u64, seqlock — odd means a write in flight) + ``length`` (u64).
HEADER = struct.Struct("<QQ")

#: The file grows in whole steps of this, so growth is rare.
GROWTH_STEP = 4096

#: How many times a reader retries a torn read before erroring out loud.
READ_ATTEMPTS = 5

#: How long a reader waits between torn-read attempts, in seconds.
READ_RETRY_SECONDS = 0.001

__all__ = [
    "GROWTH_STEP",
    "GlobalStorePublisher",
    "GlobalStoreView",
    "HEADER",
    "READ_ATTEMPTS",
    "READ_RETRY_SECONDS",
]


class GlobalStorePublisher:
    """The commander's half: publish the whole store after every applied write.

    Args:
        path: the map file; created (with its parents) at construction, and
            published EMPTY right away, so a reader never races the first write.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        self._size = 0
        self._mm: mmap.mmap | None = None
        self._seq = 0
        self._grow_to(GROWTH_STEP)
        self.publish(Bag())

    def publish(self, store: Bag) -> int:
        """Encode ``store`` and make it the published version.

        Args:
            store: the commander's global register, as it stands.

        Returns:
            The sequence number the new version carries.

        Acts on the map file, under the seqlock discipline: readers of the
        previous version stay whole, readers arriving mid-write retry.
        """
        encoded = to_tytx(store, "json")
        body = encoded if isinstance(encoded, bytes) else encoded.encode("utf-8")
        needed = HEADER.size + len(body)
        if needed > self._size:
            self._grow_to(-(-needed // GROWTH_STEP) * GROWTH_STEP)
        mm = self._mm
        assert mm is not None
        self._seq += 1  # odd: a write is in flight
        HEADER.pack_into(mm, 0, self._seq, len(body))
        mm[HEADER.size : HEADER.size + len(body)] = body
        self._seq += 1  # even: the version is whole
        HEADER.pack_into(mm, 0, self._seq, len(body))
        return self._seq

    def close(self) -> None:
        """Release the map and the descriptor; the file stays for late readers."""
        if self._mm is not None:
            self._mm.close()
            self._mm = None
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def _grow_to(self, size: int) -> None:
        """Extend the file to ``size`` bytes and map it again."""
        if self._mm is not None:
            self._mm.close()
        os.ftruncate(self._fd, size)
        self._size = size
        self._mm = mmap.mmap(self._fd, size)


class GlobalStoreView:
    """A worker's half: the published store, decoded once per version.

    Args:
        path: the same map file the commander publishes to.

    The file is opened lazily at the first read, so a view can be constructed
    before the publisher exists — a child process is built from its config
    first and speaks later.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._mm: mmap.mmap | None = None
        self._cached_seq: int | None = None
        self._cached_store: Bag | None = None
        self._lock = threading.Lock()

    @property
    def store(self) -> Bag:
        """The published global store, at its latest whole version.

        Returns:
            The decoded Bag — the reader's own copy: writing it changes
            nothing anywhere; writes travel on the lane.

        Raises:
            FileNotFoundError: nothing has ever been published at this path.
            RuntimeError: the read stayed torn past its retries.
        """
        with self._lock:
            for _ in range(READ_ATTEMPTS):
                store = self._read_once()
                if store is not None:
                    return store
                time.sleep(READ_RETRY_SECONDS)
            raise RuntimeError(f"global store view: torn read persists on {self.path}")

    def close(self) -> None:
        """Release the map; the cached Bag stays readable by whoever holds it."""
        if self._mm is not None:
            self._mm.close()
            self._mm = None

    def _read_once(self) -> Bag | None:
        """One seqlock round: the cached Bag, a fresh decode, or None on a torn read."""
        mm = self._mapped()
        seq, length = HEADER.unpack_from(mm, 0)
        if seq % 2:
            return None
        if seq == self._cached_seq:
            return self._cached_store
        if HEADER.size + length > len(mm):
            mm = self._mapped(remap=True)
        body = bytes(mm[HEADER.size : HEADER.size + length])
        seq_after, _ = HEADER.unpack_from(mm, 0)
        if seq_after != seq:
            return None
        store = from_tytx(body.decode("utf-8"), "json")
        self._cached_seq = seq
        self._cached_store = store
        return store

    def _mapped(self, remap: bool = False) -> mmap.mmap:
        """The read-only map of the file, opened on first use, remapped on growth."""
        if self._mm is None or remap:
            if self._mm is not None:
                self._mm.close()
            fd = os.open(self.path, os.O_RDONLY)
            try:
                self._mm = mmap.mmap(fd, 0, prot=mmap.PROT_READ)
            finally:
                os.close(fd)
        return self._mm
