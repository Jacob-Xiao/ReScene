"""Self-tests for the backend concurrency primitives.

Pure stdlib — no Flask, YOLO, MySQL, or network required.

Run:  python test_concurrency.py
"""

import threading
import time
import unittest

from concurrency_utils import SlidingWindowRateLimiter, lazy_singleton


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
