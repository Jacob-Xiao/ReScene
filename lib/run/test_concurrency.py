"""Self-tests for the backend concurrency primitives.

Pure stdlib — no Flask, YOLO, MySQL, or network required.

Run:  python test_concurrency.py
"""

import threading
import time
import unittest

from concurrency_utils import (
    BoundedConcurrencyGate,
    MetricsRegistry,
    SlidingWindowRateLimiter,
    lazy_singleton,
    retry_call,
)


class SlidingWindowRateLimiterTests(unittest.TestCase):
    def test_allows_up_to_limit_then_blocks(self):
        limiter = SlidingWindowRateLimiter(3, window_seconds=60)
        self.assertTrue(limiter.allow("a"))
        self.assertTrue(limiter.allow("a"))
        self.assertTrue(limiter.allow("a"))
        self.assertFalse(limiter.allow("a"), "4th hit within the window must be blocked")

    def test_keys_are_isolated(self):
        limiter = SlidingWindowRateLimiter(1, window_seconds=60)
        self.assertTrue(limiter.allow("client-1"))
        self.assertFalse(limiter.allow("client-1"))
        self.assertTrue(limiter.allow("client-2"), "different key has its own window")

    def test_window_slides(self):
        limiter = SlidingWindowRateLimiter(1, window_seconds=0.2)
        self.assertTrue(limiter.allow("a"))
        self.assertFalse(limiter.allow("a"))
        time.sleep(0.25)
        self.assertTrue(limiter.allow("a"), "old hit must expire out of the window")

    def test_retry_after_is_bounded_by_window(self):
        limiter = SlidingWindowRateLimiter(1, window_seconds=0.5)
        limiter.allow("a")
        limiter.allow("a")  # rejected, window still full
        retry = limiter.retry_after("a")
        self.assertGreaterEqual(retry, 0.0)
        self.assertLessEqual(retry, 0.5)

    def test_rejected_hits_do_not_consume_quota(self):
        limiter = SlidingWindowRateLimiter(2, window_seconds=60)
        limiter.allow("a")
        limiter.allow("a")
        for _ in range(10):
            limiter.allow("a")  # all rejected
        # Window still holds exactly 2 hits, so after expiry both slots free up.
        time.sleep(0.0)
        self.assertEqual(limiter.retry_after("a") <= 60.0, True)

    def test_thread_safety_exact_admission(self):
        """64 threads race a 10-slot limiter: exactly 10 must get through."""
        limiter = SlidingWindowRateLimiter(10, window_seconds=60)
        allowed = []
        lock = threading.Lock()
        barrier = threading.Barrier(64)

        def worker(i: int):
            barrier.wait()  # maximize contention
            ok = limiter.allow("shared")
            with lock:
                if ok:
                    allowed.append(i)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(64)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            len(allowed),
            10,
            "limiter must admit exactly max_requests under contention",
        )

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(0)
        with self.assertRaises(ValueError):
            SlidingWindowRateLimiter(1, window_seconds=0)


class LazySingletonTests(unittest.TestCase):
    def test_same_instance_across_threads(self):
        get = lazy_singleton(lambda: object())
        first = get()
        barrier = threading.Barrier(32)
        instances = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            instance = get()
            with lock:
                instances.append(instance)

        threads = [threading.Thread(target=worker) for _ in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertTrue(all(inst is first for inst in instances))

    def test_factory_called_only_once(self):
        calls = []

        def factory():
            calls.append(1)
            return {"value": 42}

        get = lazy_singleton(factory)
        get()
        get()
        get()
        self.assertEqual(len(calls), 1)
        self.assertEqual(get()["value"], 42)


class SemaphoreBackpressureTests(unittest.TestCase):
    """Mirrors the YOLO inference gate used in app_DB.py."""

    def test_acquire_times_out_when_saturated(self):
        sem = threading.Semaphore(1)
        self.assertTrue(sem.acquire(blocking=False))
        started = time.monotonic()
        acquired = sem.acquire(timeout=0.2)
        elapsed = time.monotonic() - started
        self.assertFalse(acquired, "saturated semaphore must not be acquired")
        self.assertGreaterEqual(elapsed, 0.15)
        self.assertLess(elapsed, 2.0)

    def test_release_unblocks_next_waiter(self):
        sem = threading.Semaphore(1)
        sem.acquire(blocking=False)
        result = {}

        def waiter():
            result["acquired"] = sem.acquire(timeout=5)

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.1)
        sem.release()
        t.join(timeout=5)
        self.assertTrue(result.get("acquired"))


class RateLimiterEvictionTests(unittest.TestCase):
    """The key map must not grow once per client for the process lifetime."""

    def test_expired_keys_are_evicted(self):
        # sweep_interval=1 sweeps on every call, so the test needs no sleeping
        # in a background loop.
        limiter = SlidingWindowRateLimiter(1, window_seconds=0.2, sweep_interval=1)
        limiter.allow("client-a")
        self.assertEqual(limiter.snapshot()["tracked_keys"], 1)

        time.sleep(0.25)
        limiter.allow("client-b")  # triggers the sweep

        snapshot = limiter.snapshot()
        self.assertEqual(snapshot["tracked_keys"], 1, "expired key should be swept")
        self.assertGreaterEqual(snapshot["evicted_keys_total"], 1)

    def test_active_keys_are_not_evicted(self):
        limiter = SlidingWindowRateLimiter(5, window_seconds=60, sweep_interval=1)
        limiter.allow("client-a")
        limiter.allow("client-b")
        limiter.allow("client-a")

        snapshot = limiter.snapshot()
        self.assertEqual(snapshot["tracked_keys"], 2)
        self.assertEqual(snapshot["evicted_keys_total"], 0)

    def test_many_distinct_clients_do_not_accumulate(self):
        limiter = SlidingWindowRateLimiter(1, window_seconds=0.1, sweep_interval=8)
        for i in range(200):
            limiter.allow("client-%d" % i)
            if i % 20 == 0:
                time.sleep(0.12)
        # Far fewer keys tracked than the 200 distinct clients seen.
        self.assertLess(limiter.snapshot()["tracked_keys"], 100)

    def test_eviction_restores_full_quota(self):
        limiter = SlidingWindowRateLimiter(2, window_seconds=0.2, sweep_interval=1)
        self.assertTrue(limiter.allow("a"))
        self.assertTrue(limiter.allow("a"))
        self.assertFalse(limiter.allow("a"))
        time.sleep(0.25)
        self.assertTrue(limiter.allow("a"), "quota must be restored after eviction")


class BoundedConcurrencyGateTests(unittest.TestCase):
    """Mirrors the YOLO admission gate used in app_DB.py."""

    def test_admits_up_to_capacity(self):
        gate = BoundedConcurrencyGate(capacity=2, max_waiters=0, queue_timeout=0.2)
        self.assertTrue(gate.try_acquire())
        self.assertTrue(gate.try_acquire())
        self.assertFalse(gate.try_acquire(), "third holder must be rejected")
        self.assertEqual(gate.snapshot()["rejected_queue_full"], 1)
        self.assertEqual(gate.snapshot()["rejected_timeout"], 0)

    def test_zero_waiters_rejects_instantly(self):
        gate = BoundedConcurrencyGate(capacity=1, max_waiters=0, queue_timeout=30)
        gate.try_acquire()
        started = time.monotonic()
        self.assertFalse(gate.try_acquire())
        self.assertLess(time.monotonic() - started, 0.5, "must not wait when the queue is full")

    def test_full_queue_rejects_while_slot_is_held(self):
        gate = BoundedConcurrencyGate(capacity=1, max_waiters=1, queue_timeout=5)
        self.assertTrue(gate.try_acquire())  # holds the only slot

        waiter_started = threading.Event()
        waiter_done = threading.Event()

        def waiter():
            waiter_started.set()
            gate.try_acquire()
            waiter_done.set()

        thread = threading.Thread(target=waiter)
        thread.start()
        waiter_started.wait(timeout=2)
        deadline = time.monotonic() + 2
        while gate.snapshot()["waiting"] < 1 and time.monotonic() < deadline:
            time.sleep(0.005)

        self.assertEqual(gate.snapshot()["waiting"], 1)
        started = time.monotonic()
        self.assertFalse(gate.try_acquire(), "queue is full; must reject immediately")
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(gate.snapshot()["rejected_queue_full"], 1)

        gate.release()
        self.assertTrue(waiter_done.wait(timeout=2))
        thread.join(timeout=2)

    def test_times_out_when_slot_never_frees(self):
        gate = BoundedConcurrencyGate(capacity=1, max_waiters=4, queue_timeout=0.2)
        gate.try_acquire()
        started = time.monotonic()
        self.assertFalse(gate.try_acquire())
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.15)
        self.assertLess(elapsed, 2.0)
        self.assertEqual(gate.snapshot()["rejected_timeout"], 1)

    def test_context_manager_releases_slot(self):
        gate = BoundedConcurrencyGate(capacity=1, max_waiters=0, queue_timeout=0.2)
        with gate.acquire() as acquired:
            self.assertTrue(acquired)
            self.assertEqual(gate.snapshot()["active"], 1)
        self.assertEqual(gate.snapshot()["active"], 0)
        self.assertTrue(gate.try_acquire(), "slot must be reusable after the block")
        gate.release()

    def test_context_manager_is_a_noop_when_rejected(self):
        gate = BoundedConcurrencyGate(capacity=1, max_waiters=0, queue_timeout=0.2)
        gate.try_acquire()
        with gate.acquire() as acquired:
            self.assertFalse(acquired)
        self.assertEqual(gate.snapshot()["active"], 1, "rejection must not release the holder")

    def test_double_release_is_rejected_and_state_survives(self):
        # A stray release is a caller bug, so BoundedSemaphore turns it into a
        # loud error rather than silently inflating capacity.
        gate = BoundedConcurrencyGate(capacity=1, max_waiters=0, queue_timeout=0.2)
        with self.assertRaises(ValueError):
            gate.release()

        self.assertEqual(gate.snapshot()["active"], 0)
        self.assertTrue(gate.try_acquire(), "capacity must stay intact after a stray release")
        gate.release()
        self.assertEqual(gate.snapshot()["active"], 0)
        self.assertEqual(gate.snapshot()["admitted_total"], 1)

    def test_never_exceeds_capacity_under_load(self):
        gate = BoundedConcurrencyGate(capacity=3, max_waiters=100, queue_timeout=10)
        lock = threading.Lock()
        current = [0]
        peak = [0]
        admitted = [0]
        barrier = threading.Barrier(24)

        def worker():
            barrier.wait()
            with gate.acquire() as acquired:
                if not acquired:
                    return
                with lock:
                    current[0] += 1
                    admitted[0] += 1
                    peak[0] = max(peak[0], current[0])
                time.sleep(0.01)
                with lock:
                    current[0] -= 1

        threads = [threading.Thread(target=worker) for _ in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(admitted[0], 24, "no request should be dropped when capacity suffices")
        self.assertLessEqual(peak[0], 3, "capacity must never be exceeded")
        self.assertEqual(gate.snapshot()["active"], 0)
        self.assertEqual(gate.snapshot()["waiting"], 0)

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            BoundedConcurrencyGate(capacity=0)
        with self.assertRaises(ValueError):
            BoundedConcurrencyGate(max_waiters=-1)
        with self.assertRaises(ValueError):
            BoundedConcurrencyGate(queue_timeout=0)


class MetricsRegistryTests(unittest.TestCase):
    def test_counts_accumulate(self):
        registry = MetricsRegistry()
        registry.inc("requests_total")
        registry.inc("requests_total", 4)
        self.assertEqual(registry.get("requests_total"), 5)
        self.assertEqual(registry.get("missing"), 0)

    def test_snapshot_is_a_copy(self):
        registry = MetricsRegistry()
        registry.inc("a")
        snapshot = registry.snapshot()
        snapshot["a"] = 999
        self.assertEqual(registry.get("a"), 1)

    def test_concurrent_increments_are_exact(self):
        registry = MetricsRegistry()
        barrier = threading.Barrier(32)

        def worker():
            barrier.wait()
            for _ in range(100):
                registry.inc("hits")

        threads = [threading.Thread(target=worker) for _ in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(registry.get("hits"), 3200)


class RetryCallTests(unittest.TestCase):
    def test_returns_first_success(self):
        calls = []

        def func():
            calls.append(1)
            return "ok"

        self.assertEqual(retry_call(func, retries=3, backoff=0), "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_then_succeeds(self):
        attempts = []

        def func():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("transient")
            return "recovered"

        self.assertEqual(retry_call(func, retries=3, backoff=0), "recovered")
        self.assertEqual(len(attempts), 3)

    def test_reraises_last_error_after_exhausting(self):
        attempts = []

        def func():
            attempts.append(1)
            raise ValueError("still broken")

        with self.assertRaises(ValueError):
            retry_call(func, retries=3, backoff=0)
        self.assertEqual(len(attempts), 3)

    def test_reports_each_failure(self):
        seen = []

        def func():
            raise RuntimeError("nope")

        with self.assertRaises(RuntimeError):
            retry_call(func, retries=2, backoff=0, on_error=lambda exc, i: seen.append((str(exc), i)))
        self.assertEqual(seen, [("nope", 0), ("nope", 1)])

    def test_unlisted_exception_is_not_retried(self):
        attempts = []

        def func():
            attempts.append(1)
            raise KeyError("unexpected")

        with self.assertRaises(KeyError):
            retry_call(func, retries=3, backoff=0, exceptions=(ValueError,))
        self.assertEqual(len(attempts), 1)

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            retry_call(lambda: None, retries=0)
        with self.assertRaises(ValueError):
            retry_call(lambda: None, backoff=-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
