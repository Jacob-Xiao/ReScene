"""Concurrency primitives for the ReScene backend.

Pure stdlib so the logic is unit-testable without Flask, YOLO, or the DB.
"""

import contextlib
import os
import threading
import time
from collections import deque

if os.name == "nt":  # pragma: no cover - platform specific
    import msvcrt
else:  # pragma: no cover - platform specific
    import fcntl


def _lock_byte(handle, offset: int) -> bool:
    """Try to take an exclusive lock on one byte. False when already held."""
    try:
        if os.name == "nt":
            handle.seek(offset)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.lockf(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB, 1, offset, os.SEEK_SET)
        return True
    except OSError:
        return False


def _unlock_byte(handle, offset: int) -> bool:
    try:
        if os.name == "nt":
            handle.seek(offset)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.lockf(handle.fileno(), fcntl.LOCK_UN, 1, offset, os.SEEK_SET)
        return True
    except OSError:
        return False


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter keyed by arbitrary strings.

    allow(key) records a hit and returns True while fewer than `max_requests`
    hits occurred within the trailing `window_seconds`; otherwise it returns
    False without recording anything.

    Keys whose newest hit has left the window carry no state that can still
    affect an admission decision, so they are swept periodically. Without that
    sweep the key map grows once per distinct client (IP or user id) for the
    lifetime of the process — a slow leak on a long-running server.
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0, sweep_interval: int = 512):
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict = {}
        self._lock = threading.Lock()
        self._calls = 0
        self._sweep_interval = max(1, int(sweep_interval))
        self._evicted = 0

    def _prune(self, hits: deque, now: float) -> None:
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

    def _evict_expired(self, now: float) -> None:
        """Drop keys whose every hit has aged out of the window."""
        cutoff = now - self.window_seconds
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]
        self._evicted += len(stale)

    def allow(self, key: str = "global") -> bool:
        now = time.monotonic()
        with self._lock:
            self._calls += 1
            if self._calls % self._sweep_interval == 0:
                self._evict_expired(now)

            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
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

    def snapshot(self) -> dict:
        """Live limiter state, for /health capacity reporting."""
        with self._lock:
            return {
                "max_requests": self.max_requests,
                "window_seconds": self.window_seconds,
                "tracked_keys": len(self._hits),
                "evicted_keys_total": self._evicted,
            }


class BoundedConcurrencyGate:
    """Concurrency cap with a bounded wait queue.

    At most `capacity` holders run at once and at most `max_waiters` callers may
    block for a slot; anyone beyond that is rejected immediately.

    The bound matters as much as the cap: a request waiting on a slot has
    already buffered its (possibly multi-megabyte) image in memory, so an
    unbounded queue turns a burst into unbounded memory growth — and the caller
    still eventually gets a timeout, just after doing all that damage.
    Rejecting early converts that into a fast, retryable 503.
    """

    def __init__(
        self,
        capacity: int = 1,
        max_waiters: int = 8,
        queue_timeout: float = 120.0,
    ):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if max_waiters < 0:
            raise ValueError("max_waiters must be >= 0")
        if queue_timeout <= 0:
            raise ValueError("queue_timeout must be > 0")
        self.capacity = capacity
        self.max_waiters = max_waiters
        self.queue_timeout = float(queue_timeout)
        self._semaphore = threading.BoundedSemaphore(capacity)
        self._lock = threading.Lock()
        self._active = 0
        self._waiting = 0
        self._admitted = 0
        self._rejected_queue_full = 0
        self._rejected_timeout = 0

    def try_acquire(self, timeout: float = None) -> bool:
        """Take a slot, waiting up to `timeout` (default: queue_timeout).

        Returns False when the wait queue is already full, or when no slot
        became free in time.
        """
        # A free slot is taken without consuming wait-queue budget; only callers
        # that actually have to block count against max_waiters.
        if self._semaphore.acquire(blocking=False):
            with self._lock:
                self._active += 1
                self._admitted += 1
            return True

        wait_for = self.queue_timeout if timeout is None else float(timeout)
        with self._lock:
            if self._waiting >= self.max_waiters:
                self._rejected_queue_full += 1
                return False
            self._waiting += 1
        try:
            acquired = self._semaphore.acquire(timeout=wait_for)
        finally:
            with self._lock:
                self._waiting -= 1

        with self._lock:
            if acquired:
                self._active += 1
                self._admitted += 1
            else:
                self._rejected_timeout += 1
        return acquired

    def release(self) -> None:
        with self._lock:
            if self._active > 0:
                self._active -= 1
        self._semaphore.release()

    @contextlib.contextmanager
    def acquire(self, timeout: float = None):
        """Context manager yielding whether a slot was obtained.

        Usage::

            with gate.acquire() as acquired:
                if not acquired:
                    return busy_response()
                ...work...
        """
        acquired = self.try_acquire(timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "capacity": self.capacity,
                "cross_process": False,
                "max_waiters": self.max_waiters,
                "queue_timeout_s": self.queue_timeout,
                "active": self._active,
                "waiting": self._waiting,
                "admitted_total": self._admitted,
                "rejected_queue_full": self._rejected_queue_full,
                "rejected_timeout": self._rejected_timeout,
            }


class CrossProcessGate:
    """Host-wide concurrency cap backed by a lock file.

    `BoundedConcurrencyGate` only limits one process. Two server processes on
    the same host therefore each run `MAX_YOLO_CONCURRENCY` predictions, so a
    single GPU is oversubscribed in exactly the way the in-process gate exists
    to prevent.

    This gate takes at most `capacity` slots host-wide by locking distinct bytes
    of a shared file, and defers to a local `BoundedConcurrencyGate` so
    in-process waiting stays bounded. One instance still uses the whole budget;
    N instances divide it.

    Machine-local by construction: the limit holds only between processes that
    share a filesystem. Across machines the correct answer is a distributed lock
    or a dedicated inference service.

    If the lock file is unusable the gate degrades to in-process limiting and
    reports `cross_process: False` — it never silently fails open.
    """

    def __init__(
        self,
        capacity: int,
        lock_path: str,
        max_waiters: int = 8,
        queue_timeout: float = 120.0,
        poll_interval: float = 0.05,
    ):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = int(capacity)
        self.lock_path = lock_path
        self.queue_timeout = float(queue_timeout)
        self.poll_interval = max(0.01, float(poll_interval))
        self._local = BoundedConcurrencyGate(capacity, max_waiters, queue_timeout)
        self._held = set()
        self._held_lock = threading.Lock()
        self._handle = None
        self._error = None
        self._unlock_failures = 0
        self._cross_process = self._open_lock_file()

    def _open_lock_file(self) -> bool:
        try:
            directory = os.path.dirname(os.path.abspath(self.lock_path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            handle = open(self.lock_path, "a+b")
            if os.path.getsize(self.lock_path) < self.capacity:
                handle.write(b"\0" * self.capacity)
                handle.flush()
            self._handle = handle
            return True
        except OSError as exc:
            self._error = str(exc)
            self._handle = None
            return False

    def _try_take_host_slot(self):
        with self._held_lock:
            for offset in range(self.capacity):
                # POSIX record locks are per process, so re-locking a byte this
                # process already holds would succeed and hand out a phantom
                # slot. Offsets this process owns are therefore skipped.
                if offset in self._held:
                    continue
                if _lock_byte(self._handle, offset):
                    self._held.add(offset)
                    return offset
        return None

    def _wait_for_host_slot(self, wait_for: float) -> bool:
        deadline = time.monotonic() + wait_for
        while True:
            if self._try_take_host_slot() is not None:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(self.poll_interval)

    def try_acquire(self, timeout: float = None) -> bool:
        wait_for = self.queue_timeout if timeout is None else float(timeout)
        if not self._local.try_acquire(wait_for):
            return False
        if not self._cross_process:
            return True
        if self._wait_for_host_slot(wait_for):
            return True
        # No host-wide slot available: hand the local one back.
        self._local.release()
        return False

    def release(self) -> None:
        if self._cross_process:
            with self._held_lock:
                offset = self._held.pop() if self._held else None
            if offset is not None and not _unlock_byte(self._handle, offset):
                with self._held_lock:
                    self._unlock_failures += 1
        self._local.release()

    @contextlib.contextmanager
    def acquire(self, timeout: float = None):
        acquired = self.try_acquire(timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release()

    def snapshot(self) -> dict:
        with self._held_lock:
            held = len(self._held)
        return {
            "capacity": self.capacity,
            "cross_process": self._cross_process,
            "lock_path": self.lock_path if self._cross_process else None,
            "lock_error": self._error,
            "host_slots_held": held,
            "unlock_failures": self._unlock_failures,
            "local": self._local.snapshot(),
        }

    def close(self) -> None:
        """Release held slots and close the lock file.

        Needed before deleting the lock file on Windows, where an open handle
        blocks the unlink. The running server never calls this, since the handle
        is meant to live for the process lifetime.
        """
        with self._held_lock:
            offsets = list(self._held)
            self._held.clear()
        if self._cross_process:
            for offset in offsets:
                _unlock_byte(self._handle, offset)
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None
        self._cross_process = False


class MetricsRegistry:
    """Thread-safe named counters surfaced by /health for capacity planning."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict = {}

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def get(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._counters)


def retry_call(func, retries: int = 3, backoff: float = 0.05, exceptions=(Exception,), on_error=None):
    """Call ``func()``, retrying on ``exceptions`` with linear backoff.

    Returns the first successful result and re-raises the last error once every
    attempt is exhausted. Used to ride out transient contention (an empty DB
    connection pool) instead of surfacing it to the client as a hard failure.
    """
    if retries < 1:
        raise ValueError("retries must be >= 1")
    if backoff < 0:
        raise ValueError("backoff must be >= 0")

    last = None
    for attempt in range(retries):
        try:
            return func()
        except exceptions as exc:
            last = exc
            if on_error is not None:
                on_error(exc, attempt)
            if attempt + 1 < retries:
                time.sleep(backoff * (attempt + 1))
    raise last


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
