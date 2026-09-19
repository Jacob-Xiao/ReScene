"""Runtime load test against a REAL waitress-served ReScene backend.

Unlike `test_concurrency.py` (pure primitives, in-process) this boots the actual
server as a child process and drives it over HTTP, so it exercises the things
unit tests cannot: waitress thread scheduling, the WSGI layer, the rate limiter
under genuine contention, the 503 mappings, and the degraded-mode contract.

The server is started without a database and without OpenCV/ultralytics on
purpose — that is the deployment failure mode the graceful-degradation work
targets, and it keeps the test free of GPU, model weights and MySQL.

Usage:
    python runtime_load_test.py            # boot a private server, run, report
    python runtime_load_test.py --keep     # leave the server running afterwards
    python runtime_load_test.py --url http://127.0.0.1:5000   # target an existing one
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(APP_DIR, "app_DB.py")

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import auth_utils  # noqa: E402  (needs APP_DIR on sys.path)

# Deliberately tiny so the limiter saturates within the test window.
TEST_RATE_LIMIT = 10
LIMITER_PROBES = 30
TEST_AUTH_SECRET = "runtime-load-test-secret"
TEST_USER_ID = 4242

# Concurrency levels for the throughput ramp; the request count is fixed so the
# levels are comparable.
RAMP = [1, 8, 32, 64]
RAMP_REQUESTS = 128


class Failure(Exception):
    """An invariant the run was supposed to hold did not."""


class Checks:
    def __init__(self):
        self.passed = 0
        self.failures = []

    def ok(self, condition, label, detail=""):
        if condition:
            self.passed += 1
            print("  PASS  %s" % label)
        else:
            self.failures.append("%s%s" % (label, (": " + detail) if detail else ""))
            print("  FAIL  %s%s" % (label, (" -- " + detail) if detail else ""))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(url, timeout=30, method="GET", origin=None, token=None):
    """One HTTP call; always returns a dict, never raises for HTTP errors."""
    req = urllib.request.Request(url, method=method)
    if origin:
        req.add_header("Origin", origin)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        headers = {k.lower(): v for k, v in exc.headers.items()}
        status = exc.code
    except Exception as exc:  # connection refused, timeout, ...
        return {"status": 0, "error": repr(exc), "latency": time.perf_counter() - start, "body": ""}
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    return {
        "status": status,
        "latency": time.perf_counter() - start,
        "body": body,
        "json": parsed,
        "headers": headers,
    }


def wait_for_server(base, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = request(base + "/health", timeout=5)
        if result["status"] == 200:
            return True
        time.sleep(0.25)
    return False


def start_server(port):
    """Launch the real server in degraded mode (no DB, no OpenCV)."""
    env = dict(os.environ)
    env.update(
        {
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "SERVER_THREADS": "8",
            "RATE_LIMIT_PER_MINUTE": str(TEST_RATE_LIMIT),
            "AUTH_SECRET": TEST_AUTH_SECRET,
            # Point the DB at a dead port so startup fails fast and predictably.
            "DB_HOST": "127.0.0.1",
            "DB_USER": "nobody",
            "DB_PASSWORD": "nope",
            "DB_NAME": "rescene",
            "DB_ACQUIRE_RETRIES": "1",
            "DB_ACQUIRE_BACKOFF": "0",
            # Keep the run hermetic.
            "CORS_ALLOW_ORIGINS": "",
            "IMAGE_CLEANUP_INTERVAL_S": "3600",
            "YOLO_SLOT_FILE": os.path.join(tempfile.gettempdir(), "rescene_slots_%d.lock" % port),
        }
    )
    log_path = os.path.join(tempfile.gettempdir(), "rescene_loadtest_%d.log" % port)
    handle = open(log_path, "wb")
    process = subprocess.Popen(
        [sys.executable, APP_PATH],
        cwd=APP_DIR,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    return process, log_path, handle


def stop_server(process, handle):
    try:
        process.terminate()
        process.wait(timeout=15)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
    try:
        handle.close()
    except Exception:
        pass


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * fraction))
    return ordered[index]


def ramp(base, checks):
    print("\n[1] Throughput ramp on /health (not rate limited)")
    print("    concurrency   requests   wall(s)   rps     p50(ms)  p95(ms)  non-200")
    for concurrency in RAMP:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(
                pool.map(lambda _: request(base + "/health", timeout=30), range(RAMP_REQUESTS))
            )
        wall = time.perf_counter() - started

        ok_results = [r for r in results if r["status"] == 200]
        bad = [r for r in results if r["status"] != 200]
        latencies = [r["latency"] for r in ok_results]
        rps = (len(results) / wall) if wall > 0 else 0.0
        print(
            "    %11d   %8d   %6.3f   %6.1f   %7.1f  %7.1f  %7d"
            % (
                concurrency,
                len(results),
                wall,
                rps,
                percentile(latencies, 0.5) * 1000,
                percentile(latencies, 0.95) * 1000,
                len(bad),
            )
        )
        checks.ok(not bad, "/health served every request at concurrency=%d" % concurrency,
                  "non-200: %s" % sorted({r["status"] for r in bad}))
        checks.ok(all(r["status"] != 0 for r in results), "no transport failures at concurrency=%d" % concurrency)


def check_health_contract(base, checks):
    print("\n[2] /health contract and live saturation")
    result = request(base + "/health")
    checks.ok(result["status"] == 200, "/health returns 200")
    payload = result.get("json") or {}
    checks.ok(payload.get("status") == "healthy", "/health reports healthy")

    concurrency = payload.get("concurrency") or {}
    for key in ("server_threads", "yolo_max_concurrency", "yolo_max_waiters", "db_pool_size"):
        checks.ok(key in concurrency, "/health.concurrency exposes %s" % key)

    live = payload.get("live") or {}
    checks.ok("yolo" in live, "/health.live reports the gate")
    checks.ok("db_pool" in live, "/health.live reports the DB pool")
    checks.ok("rate_limiter" in live, "/health.live reports the limiter")
    checks.ok("counters" in live, "/health.live reports counters")

    yolo = live.get("yolo") or {}
    checks.ok(yolo.get("cross_process") is True, "the YOLO gate is cross-process",
              "snapshot=%s" % yolo)
    checks.ok((yolo.get("local") or {}).get("active") == 0, "no prediction slot is held while idle")


def check_degraded_mode(base, checks):
    print("\n[3] Degraded mode: no database, no OpenCV")
    ready = request(base + "/ready")
    checks.ok(ready["status"] == 503, "/ready returns 503 while the DB is unreachable",
              "got %s" % ready["status"])
    payload = ready.get("json") or {}
    checks.ok(payload.get("ready") is False, "/ready reports ready=false")
    checks.ok((payload.get("checks") or {}).get("database") is False,
              "/ready names the database as the failing check")

    info = request(base + "/model_info")
    checks.ok(info["status"] == 503, "/model_info returns 503 (not 500) without inference",
              "got %s" % info["status"])

    # A request to the inference endpoint must be a clean 503, never a 500.
    yolo = request(base + "/yolo_seg", method="POST")
    checks.ok(yolo["status"] in (400, 429, 503), "/yolo_seg degrades without a 500",
              "got %s" % yolo["status"])

    health = request(base + "/health")
    live = (health.get("json") or {}).get("live") or {}
    checks.ok("requests_total" in (live.get("counters") or {}),
              "requests are counted even in degraded mode")


def check_rate_limiter(base, checks):
    print("\n[4] Rate limiter under real HTTP contention (%d/min, %d probes)"
          % (TEST_RATE_LIMIT, LIMITER_PROBES))

    # Authenticate so the limiter keys on the user id rather than the IP. The
    # IP bucket is shared with every other request in this run, which would make
    # an exact assertion depend on test ordering.
    token = auth_utils.make_token(TEST_USER_ID, TEST_AUTH_SECRET)
    barrier = threading.Barrier(LIMITER_PROBES)

    def probe(_):
        barrier.wait()
        return request(base + "/auth/me", token=token)

    with ThreadPoolExecutor(max_workers=LIMITER_PROBES) as pool:
        results = list(pool.map(probe, range(LIMITER_PROBES)))

    limited = [r for r in results if r["status"] == 429]
    admitted = [r for r in results if r["status"] != 429]
    statuses = sorted({r["status"] for r in results})
    print("    admitted=%d limited=%d statuses=%s" % (len(admitted), len(limited), statuses))

    checks.ok(len(admitted) == TEST_RATE_LIMIT,
              "exactly %d probes were admitted" % TEST_RATE_LIMIT, "got %d" % len(admitted))
    checks.ok(len(limited) == LIMITER_PROBES - TEST_RATE_LIMIT,
              "the rest were rejected", "got %d" % len(limited))
    checks.ok(all(r["headers"].get("retry-after") for r in limited),
              "every 429 carries Retry-After")
    # The admitted requests reach the DB, which is down: they must be 503 from
    # the PoolExhausted handler, not a 500.
    checks.ok(admitted and all(r["status"] == 503 for r in admitted),
              "DB exhaustion surfaces as 503, not 500",
              "statuses=%s" % sorted({r["status"] for r in admitted}))


def check_cors_default_off(base, checks):
    print("\n[5] CORS stays off unless configured")
    result = request(base + "/health", origin="http://example.test")
    checks.ok("access-control-allow-origin" not in result["headers"],
              "no CORS header when CORS_ALLOW_ORIGINS is empty")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="target an already-running server instead of spawning one")
    parser.add_argument("--keep", action="store_true", help="leave a spawned server running")
    args = parser.parse_args()

    process = handle = None
    if args.url:
        base = args.url.rstrip("/")
        if not wait_for_server(base, timeout=10):
            print("SKIP: no server reachable at %s" % base)
            return 0
    else:
        port = free_port()
        base = "http://127.0.0.1:%d" % port
        print("Starting backend on %s (degraded mode: no DB, no OpenCV)" % base)
        process, log_path, handle = start_server(port)
        if not wait_for_server(base):
            print("ERROR: server did not become healthy; log tail from %s:" % log_path)
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as reader:
                    for line in reader.readlines()[-30:]:
                        print("    " + line.rstrip())
            except OSError:
                pass
            stop_server(process, handle)
            return 1

    checks = Checks()
    started = time.perf_counter()
    try:
        ramp(base, checks)
        check_health_contract(base, checks)
        check_degraded_mode(base, checks)
        check_rate_limiter(base, checks)
        check_cors_default_off(base, checks)
    finally:
        elapsed = time.perf_counter() - started
        if process is not None and not args.keep:
            stop_server(process, handle)
        elif process is not None:
            print("\nServer left running (--keep): %s" % base)

    print("\n%s" % ("-" * 68))
    print("Runtime load test: %d passed, %d failed in %.1fs"
          % (checks.passed, len(checks.failures), elapsed))
    for failure in checks.failures:
        print("  FAILED: %s" % failure)
    return 1 if checks.failures else 0


if __name__ == "__main__":
    sys.exit(main())
