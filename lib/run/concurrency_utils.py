"""Concurrency primitives for the ReScene backend.

Pure stdlib so the logic is unit-testable without Flask, YOLO, or the DB.
"""

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter keyed by arbitrary strings.

    allow(key) records a hit and returns True while fewer than `max_requests`
    hits occurred within the trailing `window_seconds`; otherwise it returns
    False without recording anything.
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, hits: deque, now: float) -> None:
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

    def allow(self, key: str = "global") -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            self._prune(hits, now)
            if len(hits) < self.max_requests:
                hits.append(now)
                return True
            return False

    def retry_after(self, key: str = "global") -> float:
        """Seconds until the oldest hit in the window expires (>= 0)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0.0
            self._prune(hits, now)
            if not hits:
                return 0.0
            return max(0.0, self.window_seconds - (now - hits[0]))


def lazy_singleton(factory):
    """Double-checked-locking lazy initializer for shared clients.

    Returns a zero-argument callable that builds the instance on first use
    and always returns the same object afterwards. Used so the OpenAI client
    is only created (and only requires an API key) when /makeGPT is hit.
    """
    lock = threading.Lock()
    instance = None

    def get():
        nonlocal instance
        if instance is None:
            with lock:
                if instance is None:
                    instance = factory()
        return instance

    return get
