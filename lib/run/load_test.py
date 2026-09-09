"""Concurrent smoke/load test against a RUNNING ReScene backend.

Hits /health with N concurrent requests and reports status codes + latency.
Skips gracefully when the server is not reachable.

Usage:
    python load_test.py [concurrency] [base_url]

Examples:
    python load_test.py 64
    python load_test.py 128 http://127.0.0.1:5000
"""

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://127.0.0.1:5000"
PATH = "/health"


def fetch(url: str):
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            status = resp.status
    except urllib.error.HTTPError as e:
        body, status = {}, e.code
    except Exception as e:  # connection refused, timeout, ...
        return {"status": 0, "error": repr(e), "latency": time.perf_counter() - start}
    return {"status": status, "latency": time.perf_counter() - start, "body": body}


def main() -> int:
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    base = sys.argv[2] if len(sys.argv) > 2 else BASE_URL
    url = base.rstrip("/") + PATH

    # Probe first: skip cleanly if the backend is not running.
    probe = fetch(url)
    if probe["status"] == 0:
        print(f"SKIP: backend not reachable at {url} ({probe['error']})")
        print("Start it first:  python app_DB.py")
        return 0

    print(f"Load test: {concurrency} concurrent GET {url}")
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda _: fetch(url), range(concurrency)))
    total = time.perf_counter() - start

    ok = sum(1 for r in results if r["status"] == 200)
    limited = sum(1 for r in results if r["status"] == 429)
    failed = sum(1 for r in results if r["status"] not in (200, 429))
    latencies = sorted(r["latency"] for r in results if r["status"] == 200)

    print(f"  total time : {total:.2f}s")
    print(f"  200 OK     : {ok}/{concurrency}")
    if limited:
        print(f"  429 limited: {limited} (rate limiter working)")
    if failed:
        print(f"  other      : {failed}")
    if latencies:
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        print(f"  latency    : p50={p50*1000:.0f}ms  p95={p95*1000:.0f}ms")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
