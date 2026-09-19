"""Tests for the scaling / high-load changes.

Deliberately does NOT import app_DB: it pulls in ultralytics, OpenCV and
MySQL at import time, which would make an ordinary unit-test run depend on a
model file and a live database. Everything here is stdlib-only, and the
backend file itself is checked statically (compilation, env contract, wiring).

Run:  python test_scaling.py
"""

import os
import py_compile
import re
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import retention_utils  # noqa: E402  (import after sys.path setup)

RUN_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(RUN_DIR, "app_DB.py")
ENV_EXAMPLE_PATH = os.path.join(RUN_DIR, "env.example")

# Matches an uncommented KEY= line in env.example.
ENV_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=", re.MULTILINE)
# Matches os.getenv("KEY" ...) / os.getenv('KEY' ...)
GETENV_RE = re.compile(r"os\.getenv\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']")


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, age_seconds: float, size: int = 10) -> str:
        path = os.path.join(self.dir, name)
        with open(path, "wb") as handle:
            handle.write(b"x" * size)
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
        return path

    def test_removes_files_older_than_max_age(self):
        old = self.write("yolo_input_1.png", age_seconds=7200)
        fresh = self.write("yolo_input_2.png", age_seconds=10)

        summary = retention_utils.prune_files(self.dir, max_age_seconds=3600, max_files=100)

        self.assertEqual(summary["removed"], 1)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(fresh))

    def test_keeps_everything_when_within_both_bounds(self):
        self.write("a.png", age_seconds=1)
        self.write("b.png", age_seconds=2)

        summary = retention_utils.prune_files(self.dir, max_age_seconds=3600, max_files=10)

        self.assertEqual(summary["removed"], 0)
        self.assertEqual(summary["kept"], 2)

    def test_enforces_max_files_keeping_newest_first(self):
        newest = self.write("newest.png", age_seconds=1)
        middle = self.write("middle.png", age_seconds=100)
        oldest = self.write("oldest.png", age_seconds=200)

        summary = retention_utils.prune_files(self.dir, max_age_seconds=3600, max_files=2)

        self.assertEqual(summary["removed"], 1)
        self.assertTrue(os.path.exists(newest))
        self.assertTrue(os.path.exists(middle))
        self.assertFalse(os.path.exists(oldest))

    def test_reports_freed_bytes(self):
        self.write("big.png", age_seconds=7200, size=2048)

        summary = retention_utils.prune_files(self.dir, max_age_seconds=60, max_files=10)

        self.assertEqual(summary["removed"], 1)
        self.assertEqual(summary["freed_bytes"], 2048)

    def test_ignores_unrelated_files_and_directories(self):
        keeper = self.write("notes.txt", age_seconds=7200)
        os.mkdir(os.path.join(self.dir, "subdir"))

        summary = retention_utils.prune_files(self.dir, max_age_seconds=60, max_files=10)

        self.assertEqual(summary["removed"], 0)
        self.assertTrue(os.path.exists(keeper), "non-image files must be left alone")

    def test_missing_directory_is_not_an_error(self):
        summary = retention_utils.prune_files(
            os.path.join(self.dir, "does-not-exist"), max_age_seconds=60, max_files=10
        )
        self.assertEqual(summary["removed"], 0)
        self.assertEqual(summary["kept"], 0)

    def test_invalid_arguments_rejected(self):
        with self.assertRaises(ValueError):
            retention_utils.prune_files(self.dir, max_age_seconds=-1, max_files=10)
        with self.assertRaises(ValueError):
            retention_utils.prune_files(self.dir, max_age_seconds=60, max_files=-1)


class BackendCompilesTests(unittest.TestCase):
    def test_app_db_compiles(self):
        # Catches syntax errors without importing the heavy dependencies.
        py_compile.compile(APP_PATH, doraise=True)


class EnvContractTests(unittest.TestCase):
    """env.example is the deployment contract; drift breaks operators."""

    def setUp(self):
        self.example_keys = set(ENV_KEY_RE.findall(read(ENV_EXAMPLE_PATH)))
        self.getenv_keys = set(GETENV_RE.findall(read(APP_PATH)))

    def test_example_file_is_not_empty(self):
        self.assertGreater(len(self.example_keys), 10)

    def test_every_documented_key_is_actually_read(self):
        unused = sorted(self.example_keys - self.getenv_keys)
        self.assertEqual(unused, [], "env.example documents keys the backend never reads")

    def test_every_read_key_is_documented(self):
        undocumented = sorted(self.getenv_keys - self.example_keys)
        self.assertEqual(undocumented, [], "the backend reads keys missing from env.example")


class HardeningWiringTests(unittest.TestCase):
    """Static guards so the high-load protections cannot be silently reverted.

    These assert on source text rather than behaviour because importing app_DB
    requires YOLO weights and a database.
    """

    def setUp(self):
        self.source = read(APP_PATH)

    def assert_wired(self, needle: str) -> None:
        self.assertIn(needle, self.source, "%r is missing from app_DB.py" % needle)

    def test_cross_process_gate_is_the_default(self):
        # The default path must be host-wide, otherwise N instances on one box
        # each run MAX_YOLO_CONCURRENCY predictions and oversubscribe the GPU.
        self.assert_wired("_yolo_gate = CrossProcessGate(")
        self.assert_wired("lock_path=YOLO_SLOT_FILE")
        self.assert_wired("with _yolo_gate.acquire() as acquired:")

    def test_in_process_gate_remains_available_as_opt_out(self):
        # YOLO_SLOT_FILE="" must fall back to in-process limiting only.
        self.assert_wired("_yolo_gate = BoundedConcurrencyGate(")
        self.assert_wired("if YOLO_SLOT_FILE:")

    def test_inference_dependencies_load_lazily(self):
        # Eager imports meant a machine without OpenCV could not start at all,
        # so it could not even answer /health or be drained.
        self.assert_wired("def load_inference_deps()")
        self.assert_wired("def get_model()")
        self.assertNotIn(
            "from ultralytics import YOLO  # noqa: E402",
            self.source,
            "ultralytics must not be imported at module scope",
        )
        self.assertNotIn(
            "\nimport cv2\n",
            self.source,
            "opencv must not be imported at module scope",
        )

    def test_weights_are_not_loaded_at_import(self):
        self.assertNotIn(
            "model = YOLO(MODEL_PATH)",
            self.source,
            "weights must load on first use, not at import",
        )
        self.assert_wired("model = get_model()")

    def test_inference_unavailable_maps_to_503(self):
        self.assert_wired("class InferenceUnavailable(RuntimeError)")
        self.assert_wired("@app.errorhandler(InferenceUnavailable)")

    def test_database_failure_does_not_abort_startup(self):
        self.assert_wired("Database unavailable at startup; DB-backed endpoints will answer 503")

    def test_ollama_uses_a_thread_local_session(self):
        self.assert_wired("def get_http_session()")
        self.assert_wired("get_http_session().post(OLLAMA_URL")
        # The old shared module-level session must not come back.
        self.assertNotIn("_http_session = requests.Session()", self.source)

    def test_openai_client_has_a_timeout(self):
        self.assert_wired("timeout=OPENAI_TIMEOUT")
        self.assert_wired("max_retries=OPENAI_MAX_RETRIES")

    def test_db_pool_exhaustion_maps_to_503(self):
        self.assert_wired("class PoolExhausted(RuntimeError)")
        self.assert_wired("@app.errorhandler(PoolExhausted)")
        self.assert_wired('response.headers["Retry-After"] = "5"')

    def test_readiness_probe_exists(self):
        self.assert_wired('@app.route("/ready", methods=["GET"])')

    def test_health_reports_live_saturation(self):
        self.assert_wired('"live": {')
        self.assert_wired("_yolo_gate.snapshot()")

    def test_cors_is_opt_in(self):
        self.assert_wired("@app.after_request")
        self.assert_wired("CORS_ALLOW_ORIGINS")

    def test_image_retention_is_started(self):
        self.assert_wired("def start_image_cleanup()")
        self.assert_wired("start_image_cleanup()")
        self.assert_wired("retention_utils.prune_files(")


if __name__ == "__main__":
    unittest.main(verbosity=2)
