"""Short-lived in-memory storage. Uploaded datasheets are never written to disk."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable


class TTLStore[V]:
    """Thread-safe dict with per-entry expiry and a maximum size (oldest evicted first)."""

    def __init__(
        self, ttl_seconds: float, max_items: int, clock: Callable[[], float] = time.monotonic
    ):
        self._ttl = ttl_seconds
        self._max = max_items
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, key: str, value: V) -> None:
        with self._lock:
            self._purge()
            self._items.pop(key, None)
            self._items[key] = (self._clock() + self._ttl, value)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def get(self, key: str) -> V | None:
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            expires, value = entry
            if expires < self._clock():
                del self._items[key]
                return None
            return value

    def touch(self, key: str) -> None:
        """Extend an entry's lifetime (e.g. while a check run is using it)."""
        with self._lock:
            entry = self._items.get(key)
            if entry is not None:
                self._items[key] = (self._clock() + self._ttl, entry[1])

    def __len__(self) -> int:
        with self._lock:
            self._purge()
            return len(self._items)

    def _purge(self) -> None:
        now = self._clock()
        for key in [k for k, (exp, _) in self._items.items() if exp < now]:
            del self._items[key]
