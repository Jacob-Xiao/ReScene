"""Multi-process tests for the cross-process inference gate.

These spawn REAL OS processes that contend for the same lock file, which is the
only way to test the claim that matters: that running several server instances
on one host does not multiply the GPU budget.

Two experiments run here:

1. control — `BoundedConcurrencyGate` is per process, so N processes admit N
   concurrent holders. This is the failure the cross-process gate exists to fix.
2. fix — `CrossProcessGate` caps holders host-wide, so N processes still admit
   only `capacity`.

Run:  python test_multiprocess.py
"""

import multiprocessing
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from concurrency_utils import BoundedConcurrencyGate, CrossProcessGate  # noqa: E402

HOLD_SECONDS = 0.25
WAIT_SECONDS = 5.0
START_SKEW = 0.6


def _write_result(out_dir, index, acquired_at, released_at):
    path = os.path.join(out_dir, "worker_%d.txt" % index)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("%d %.6f %.6f" % (index, acquired_at, released_at))


def _worker(kind, capacity, lock_path, out_dir, start_at, index):
    """Child process: contend for one slot, then record the interval held."""
    if kind == "cross_process":
        gate = CrossProcessGate(
            capacity=capacity,
            lock_path=lock_path,
            max_waiters=128,
            queue_timeout=WAIT_SECONDS,
        )
    else:
        gate = BoundedConcurrencyGate(
            capacity=capacity,
            max_waiters=128,
            queue_timeout=WAIT_SECONDS,
        )

    # Line every child up so they genuinely contend rather than running in turn.
    while time.time() < start_at:
        time.sleep(0.002)

    with gate.acquire() as acquired:
        if not acquired:
            return
        acquired_at = time.time()
        time.sleep(HOLD_SECONDS)
        _write_result(out_dir, index, acquired_at, time.time())


def max_overlap(intervals):
    """Largest number of intervals sharing a point in time."""
    events = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda event: (event[0], event[1]))
    current = peak = 0
    for _at, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


class MultiProcessGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.lock_path = os.path.join(self.dir, "slots.lock")
        self._gates = []

    def tearDown(self):
        # Windows refuses to unlink a file with an open handle, so every gate
        # this test created must be closed before the temp dir goes away.
        for gate in self._gates:
            gate.close()
        self._tmp.cleanup()

    def make_gate(self, **kwargs):
        gate = CrossProcessGate(lock_path=self.lock_path, **kwargs)
        self._gates.append(gate)
        return gate

    def run_workers(self, kind, capacity, workers):
        context = multiprocessing.get_context("spawn")
        start_at = time.time() + START_SKEW
        processes = [
            context.Process(
                target=_worker,
                args=(kind, capacity, self.lock_path, self.dir, start_at, index),
            )
            for index in range(workers)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=WAIT_SECONDS + 15)

        intervals = []
        for index in range(workers):
            path = os.path.join(self.dir, "worker_%d.txt" % index)
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as handle:
                _idx, start, end = handle.read().split()
            intervals.append((float(start), float(end)))
        return intervals

    def test_control_in_process_gate_multiplies_across_processes(self):
        """Documents the bug: one slot per process means N slots host-wide."""
        intervals = self.run_workers("in_process", capacity=1, workers=3)

        self.assertEqual(len(intervals), 3, "every worker should have been admitted")
        self.assertEqual(
            max_overlap(intervals),
            3,
            "an in-process gate cannot bind across processes — this is the defect",
        )

    def test_cross_process_gate_caps_holders_host_wide(self):
        intervals = self.run_workers("cross_process", capacity=1, workers=3)

        self.assertEqual(len(intervals), 3, "all three workers should eventually run")
        self.assertEqual(
            max_overlap(intervals),
            1,
            "the cross-process gate must keep exactly one holder host-wide",
        )

    def test_cross_process_gate_shares_a_two_slot_budget(self):
        intervals = self.run_workers("cross_process", capacity=2, workers=5)

        self.assertEqual(len(intervals), 5, "all workers should eventually run")
        self.assertEqual(max_overlap(intervals), 2, "the host-wide budget is two slots")
        self.assertLess(
            intervals[-1][1] - intervals[0][0],
            WAIT_SECONDS,
            "a 5-worker race for 2 slots must not need the full queue timeout",
        )

    def test_lock_file_is_created_and_reported(self):
        nested = os.path.join(self.dir, "nested", "s.lock")
        gate = CrossProcessGate(capacity=2, lock_path=nested)
        self._gates.append(gate)
        snapshot = gate.snapshot()

        self.assertTrue(snapshot["cross_process"], "lock file should be usable")
        self.assertIsNone(snapshot["lock_error"])
        self.assertTrue(os.path.exists(nested))

    def test_degrades_to_in_process_when_lock_file_is_unusable(self):
        # A directory can never be opened as a lock file. queue_timeout is kept
        # short: the second acquire legitimately waits out the whole queue
        # budget before giving up, which is the documented semantics.
        gate = CrossProcessGate(capacity=1, lock_path=self.dir, queue_timeout=0.2)
        self._gates.append(gate)

        snapshot = gate.snapshot()
        self.assertFalse(snapshot["cross_process"], "must report degraded mode")
        self.assertIsNotNone(snapshot["lock_error"])
        # Degraded mode still enforces the local limit rather than failing open.
        self.assertTrue(gate.try_acquire())
        self.assertFalse(gate.try_acquire())
        gate.release()

    def test_single_process_can_use_the_whole_budget(self):
        gate = self.make_gate(capacity=3, max_waiters=8, queue_timeout=0.2)
        acquired = [gate.try_acquire() for _ in range(3)]
        self.assertEqual(acquired, [True, True, True])
        self.assertFalse(gate.try_acquire(), "a fourth slot does not exist")
        for _ in range(3):
            gate.release()
        self.assertEqual(gate.snapshot()["host_slots_held"], 0)

    def test_slots_are_released_between_uses(self):
        gate = self.make_gate(capacity=1, queue_timeout=0.2)
        for _ in range(5):
            with gate.acquire() as acquired:
                self.assertTrue(acquired)
        self.assertEqual(gate.snapshot()["host_slots_held"], 0)
        self.assertEqual(gate.snapshot()["unlock_failures"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
