"""ReScene local backend.

Single consolidated server providing:
  - POST /yolo_seg      YOLO segmentation -> transparent PNG + detections
  - POST /makeGPT       OpenAI gpt-image-1 background editing
  - POST /submit_content proxy chat requests to a local Ollama instance
  - GET  /health        health check
  - GET  /model_info    YOLO model metadata
  - GET  /get_image/<filename> serve stored images from the data directory

All configuration comes from environment variables (a `.env` file next to
this script is loaded automatically — see `.env.example`).
"""

import base64
import functools
import io
import json
import logging
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

import mysql.connector
import mysql.connector.pooling
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI
from PIL import Image

import cv2
import numpy as np

import auth_utils
import retention_utils
from concurrency_utils import (
    BoundedConcurrencyGate,
    MetricsRegistry,
    SlidingWindowRateLimiter,
    lazy_singleton,
    retry_call,
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Load `.env` from the script directory first, then the working directory.
load_dotenv(os.path.join(APP_DIR, ".env"))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("rescene")

# Optional: allow running against a local ultralytics checkout instead of the
# pip-installed package (e.g. a source clone containing trained weights).
ULTRALYTICS_PATH = os.getenv("ULTRALYTICS_PATH", "")
if ULTRALYTICS_PATH and os.path.isdir(ULTRALYTICS_PATH):
    sys.path.insert(0, ULTRALYTICS_PATH)

from ultralytics import YOLO  # noqa: E402  (import after optional sys.path setup)

app = Flask(__name__)
# Local-only desktop backend: 16 MiB upload cap. CORS stays off unless
# CORS_ALLOW_ORIGINS names the browser origins that may call this server (the
# Expo web build needs it; the desktop and native clients do not).
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

_STARTED_AT = time.time()

# Live counters surfaced by /health so capacity decisions do not rely on
# guesswork.
_metrics = MetricsRegistry()


class PoolExhausted(RuntimeError):
    """No pooled database connection became available within the budget.

    Distinct from a generic failure because it is transient: the client should
    retry, so it maps to 503 + Retry-After rather than 500.
    """


def rate_limited(limiter):
    """Reject requests over the per-user/per-IP limit with 429 + Retry-After."""

    def _rate_key() -> str:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            uid = auth_utils.parse_token(auth[7:], AUTH_SECRET)
            if uid is not None:
                return f"u:{uid}"
        return "ip:" + (request.remote_addr or "unknown")

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = _rate_key()
            if not limiter.allow(key):
                _metrics.inc("rate_limited_total")
                retry = max(1, int(round(limiter.retry_after(key))))
                response = jsonify({"success": False, "error": "请求过于频繁，请稍后再试"})
                response.status_code = 429
                response.headers["Retry-After"] = str(retry)
                log.warning("Rate limited %s on %s (retry after %ds)", key, fn.__name__, retry)
                return response
            return fn(*args, **kwargs)

        return wrapper

    return decorator

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL_PATH = os.getenv("MODEL_PATH", "yolo11x-seg.pt")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "user": os.getenv("DB_USER", "rescene"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "rescene"),
    "charset": os.getenv("DB_CHARSET", "utf8mb4"),
}

# Generated images are stored on disk; only their paths go into the database.
DATA_DIR = os.path.join(APP_DIR, "data", "images")
os.makedirs(DATA_DIR, exist_ok=True)

# --- Concurrency / backpressure configuration --------------------------------
SERVER_THREADS = int(os.getenv("SERVER_THREADS", "8"))
MAX_YOLO_CONCURRENCY = int(os.getenv("MAX_YOLO_CONCURRENCY", "1"))
YOLO_QUEUE_TIMEOUT = float(os.getenv("YOLO_QUEUE_TIMEOUT", "120"))
# How many requests may block waiting for a model slot. Beyond this the server
# answers 503 at once instead of letting queued image payloads pile up in RAM.
YOLO_MAX_WAITERS = int(os.getenv("YOLO_MAX_WAITERS", "8"))
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_ACQUIRE_RETRIES = int(os.getenv("DB_ACQUIRE_RETRIES", "3"))
DB_ACQUIRE_BACKOFF = float(os.getenv("DB_ACQUIRE_BACKOFF", "0.1"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
GPT_RATE_LIMIT_PER_MINUTE = int(os.getenv("GPT_RATE_LIMIT_PER_MINUTE", "10"))

# Outbound call budgets. A stalled upstream must never pin a worker thread
# forever: with a bounded thread pool, enough hung calls take the whole server
# down even though every local component is healthy.
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "300"))
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "180"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
HTTP_POOL_SIZE = int(os.getenv("HTTP_POOL_SIZE", str(max(SERVER_THREADS, 10))))

# Generated images are pruned on a timer so the data directory cannot grow
# until the disk fills up.
IMAGE_RETENTION_DAYS = float(os.getenv("IMAGE_RETENTION_DAYS", "7"))
IMAGE_MAX_FILES = int(os.getenv("IMAGE_MAX_FILES", "2000"))
IMAGE_CLEANUP_INTERVAL_S = float(os.getenv("IMAGE_CLEANUP_INTERVAL_S", "600"))

# Opt-in CORS for browser clients; empty means "send no CORS headers at all".
CORS_ALLOW_ORIGINS = [
    origin.strip() for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if origin.strip()
]

# ultralytics inference is not guaranteed thread-safe, so at most
# MAX_YOLO_CONCURRENCY predictions run at once. The wait queue is bounded too:
# a queued request has already buffered its image, so an unbounded queue turns
# a burst into unbounded memory growth.
_yolo_gate = BoundedConcurrencyGate(
    capacity=MAX_YOLO_CONCURRENCY,
    max_waiters=YOLO_MAX_WAITERS,
    queue_timeout=YOLO_QUEUE_TIMEOUT,
)

# Per-client-IP sliding window limiters; /makeGPT gets a much stricter cap
# to protect the OpenAI quota.
_general_limiter = SlidingWindowRateLimiter(RATE_LIMIT_PER_MINUTE, window_seconds=60.0)
_gpt_limiter = SlidingWindowRateLimiter(GPT_RATE_LIMIT_PER_MINUTE, window_seconds=60.0)

_http_local = threading.local()


def get_http_session() -> requests.Session:
    """Per-thread keep-alive session for the Ollama proxy.

    requests.Session holds mutable cookie and header state and is not
    thread-safe, and the default urllib3 pool caps at 10 connections — fewer
    than the waitress thread count. Giving each worker thread its own session
    and pool stops concurrent proxied chats from starving one another.
    """
    session = getattr(_http_local, "session", None)
    if session is None:
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=2,
            pool_maxsize=HTTP_POOL_SIZE,
            max_retries=0,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _http_local.session = session
    return session


# OpenAI client is created lazily so the server can start without an API key.
# The timeout is what stops a stalled upstream from holding a worker thread
# indefinitely.
get_openai_client = lazy_singleton(
    lambda: OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=OPENAI_TIMEOUT,
        max_retries=OPENAI_MAX_RETRIES,
    )
)

# --- Authentication / membership configuration --------------------------------
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
if not AUTH_SECRET:
    AUTH_SECRET = os.urandom(32).hex()
    log.warning(
        "AUTH_SECRET not set; generated an ephemeral secret (login sessions reset on restart)"
    )

AUTH_RATE_LIMIT_PER_MINUTE = int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "20"))
_auth_limiter = SlidingWindowRateLimiter(AUTH_RATE_LIMIT_PER_MINUTE, window_seconds=60.0)

# Membership catalog. Prices are in CNY for a 30-day term; checkout is a demo
# (orders are recorded as paid immediately, no real payment gateway is called).
MEMBERSHIP_TIERS = [
    {"code": "free", "name": "Free", "price": 0.0, "days": 0,
     "features": ["YOLO image segmentation", "Llama local chat", "GPT background edits"]},
    {"code": "pro", "name": "Pro", "price": 29.0, "days": 30,
     "features": ["Everything in Free", "Priority processing queue", "Usage history"]},
    {"code": "studio", "name": "Studio", "price": 99.0, "days": 30,
     "features": ["Everything in Pro", "Batch processing (coming soon)", "Dedicated support"]},
]
TIER_BY_CODE = {t["code"]: t for t in MEMBERSHIP_TIERS}

log.info("Loading YOLO model from %s ...", MODEL_PATH)
model = YOLO(MODEL_PATH)
log.info("Model loaded (%d classes)", len(model.names))

connection_pool = None


def ensure_database_and_tables():
    """Create the database, connection pool and tables if they don't exist."""
    global connection_pool

    tmp_conn = mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        charset=DB_CONFIG.get("charset", "utf8mb4"),
        use_unicode=True,
    )
    tmp_cursor = tmp_conn.cursor()
    tmp_cursor.execute(
        "CREATE DATABASE IF NOT EXISTS `{}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;".format(
            DB_CONFIG["database"]
        )
    )
    tmp_conn.commit()
    tmp_cursor.close()
    tmp_conn.close()

    connection_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="rescene_pool",
        pool_size=DB_POOL_SIZE,
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        charset=DB_CONFIG.get("charset", "utf8mb4"),
        use_unicode=True,
    )

    conn = connection_pool.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS gpt_image_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            prompt TEXT,
            user_image_longtext LONGTEXT,
            output_image_longtext LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET = utf8mb4;
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS yolo_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            object_count INT,
            detections JSON,
            input_image_longtext LONGTEXT,
            segmented_image_longtext LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET = utf8mb4;
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(32) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(16) NOT NULL DEFAULT 'user',
            membership_tier VARCHAR(16) NOT NULL DEFAULT 'free',
            membership_expires_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) CHARACTER SET = utf8mb4;
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS membership_orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            tier VARCHAR(16) NOT NULL,
            price DECIMAL(8, 2) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'paid',
            expires_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        ) CHARACTER SET = utf8mb4;
        """
    )
    conn.commit()
    cursor.close()
    conn.close()
    log.info("Database and tables ready")


def _strip_data_url(value):
    """Return (raw_bytes, pure_base64) from a base64 string or data URL."""
    if isinstance(value, bytes):
        return value, base64.b64encode(value).decode("utf-8")
    b64 = value.split(",", 1)[1] if value.startswith("data:") else value
    return base64.b64decode(b64), b64


def save_image_bytes(data, prefix):
    """Persist raw image bytes under DATA_DIR and return the file path."""
    try:
        ext = (Image.open(io.BytesIO(data)).format or "PNG").lower()
    except Exception:
        ext = "png"
    path = os.path.join(DATA_DIR, "{}_{}.{}".format(prefix, int(time.time() * 1000), ext))
    with open(path, "wb") as f:
        f.write(data)
    return path


def _get_connection():
    """Borrow a pooled connection, retrying briefly under contention.

    mysql-connector raises PoolError the moment the pool is empty, so ordinary
    contention under a burst would surface as a 500. A short bounded retry lets
    the request either get a connection or fail as a retryable 503.
    """
    if connection_pool is None:
        raise PoolExhausted("database pool is not initialised")

    try:
        return retry_call(
            connection_pool.get_connection,
            retries=DB_ACQUIRE_RETRIES,
            backoff=DB_ACQUIRE_BACKOFF,
            exceptions=(mysql.connector.errors.PoolError,),
            on_error=lambda *_: _metrics.inc("db_pool_contention"),
        )
    except mysql.connector.errors.PoolError as exc:
        _metrics.inc("db_pool_exhausted")
        raise PoolExhausted(str(exc)) from exc


def _insert_log(sql, params):
    """Insert a log row; failures are logged but never fail the HTTP request."""
    conn = cursor = None
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
    except Exception:
        log.exception("DB insert failed")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def insert_gpt_log(prompt, user_image_path, output_image_path):
    _insert_log(
        "INSERT INTO gpt_image_logs (prompt, user_image_longtext, output_image_longtext)"
        " VALUES (%s, %s, %s)",
        (prompt, user_image_path, output_image_path),
    )


def insert_yolo_log(object_count, detections, input_image_path, segmented_image_path):
    _insert_log(
        "INSERT INTO yolo_logs (object_count, detections, input_image_longtext,"
        " segmented_image_longtext) VALUES (%s, %s, %s, %s)",
        (object_count, json.dumps(detections, ensure_ascii=False), input_image_path, segmented_image_path),
    )


def process_image_segmentation_only(image_data):
    """Run YOLO inference and return the segmented transparent-background image."""
    try:
        # Admission happens before decoding: a request waiting for a model slot
        # then holds only its compressed payload, not a decoded full-resolution
        # RGB array.
        with _yolo_gate.acquire() as acquired:
            if not acquired:
                _metrics.inc("yolo_rejected_busy")
                return {
                    "success": False,
                    "error": "服务器繁忙，请稍后重试",
                    "retry_after": 30,
                    "busy": True,
                }

            raw, _ = _strip_data_url(image_data)
            nparr = np.frombuffer(raw, np.uint8)
            orig_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if orig_img is None:
                raise ValueError("无法解码图片")

            results = model.predict(orig_img, save=False, conf=0.25, iou=0.45, verbose=False)

        # Mask assembly is CPU-only numpy work that never touches the model, so
        # it runs after the slot has been released.
        result = results[0]

        rgb_img = cv2.cvtColor(orig_img, cv2.COLOR_BGR2RGB)
        object_count = 0
        if result.masks is not None:
            masks = result.masks.data.cpu().numpy()
            object_count = len(masks)
            combined_mask = np.zeros((orig_img.shape[0], orig_img.shape[1]), dtype=np.uint8)
            for mask in masks:
                mask_resized = cv2.resize(mask, (orig_img.shape[1], orig_img.shape[0]))
                combined_mask = np.maximum(combined_mask, (mask_resized > 0.5).astype(np.uint8))

            rgba_array = np.zeros((*rgb_img.shape[:2], 4), dtype=np.uint8)
            rgba_array[..., :3] = rgb_img
            rgba_array[..., 3] = combined_mask * 255
            segmented_img = Image.fromarray(rgba_array, "RGBA")
            log.info("Segmented %d objects", len(masks))
        else:
            segmented_img = Image.fromarray(
                np.zeros((*rgb_img.shape[:2], 4), dtype=np.uint8), "RGBA"
            )
            log.info("No objects detected")

        detection_info = []
        if getattr(result, "boxes", None) is not None:
            for box in result.boxes:
                cls = int(box.cls[0])
                detection_info.append(
                    {
                        "class": cls,
                        "class_name": model.names[cls],
                        "confidence": round(float(box.conf[0]), 4),
                        "bbox": [round(x, 2) for x in box.xyxy[0].tolist()],
                    }
                )

        return {
            "success": True,
            "segmented_image": segmented_img,
            "detections": detection_info,
            "raw_input": raw,
            "original_shape": orig_img.shape,
            "has_segmentation": result.masks is not None,
            "object_count": object_count,
        }

    except Exception as e:
        log.exception("Image processing failed")
        return {"success": False, "error": str(e)}


def base64_to_temp_file(image_base64):
    """Write a base64 image to a temp file and return its path (caller cleans up)."""
    raw, _ = _strip_data_url(image_base64)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    temp_file.write(raw)
    temp_file.close()
    return temp_file.name


@app.route("/yolo_seg", methods=["POST"])
@rate_limited(_general_limiter)
def yolo_segmentation_transparent():
    start_time = time.time()
    try:
        if "image" in request.files:
            file = request.files["image"]
            if file.filename == "":
                return jsonify({"success": False, "error": "没有选择文件"}), 400
            image_data = file.read()
            log.info("Received file upload: %s (%d bytes)", file.filename, len(image_data))
        elif request.is_json and request.json.get("image"):
            image_data = request.json["image"]
        else:
            return jsonify({"success": False, "error": "没有收到图片文件"}), 400

        result = process_image_segmentation_only(image_data)
        if not result["success"]:
            status = 503 if result.get("retry_after") else 500
            return jsonify(result), status

        img_byte_arr = io.BytesIO()
        result["segmented_image"].save(img_byte_arr, format="PNG")
        segmented_bytes = img_byte_arr.getvalue()
        base64_image = base64.b64encode(segmented_bytes).decode("utf-8")
        processing_time = round(time.time() - start_time, 2)

        try:
            input_path = save_image_bytes(result["raw_input"], "yolo_input")
            output_path = save_image_bytes(segmented_bytes, "yolo_segmented")
            insert_yolo_log(
                object_count=result["object_count"],
                detections=result["detections"],
                input_image_path=input_path,
                segmented_image_path=output_path,
            )
        except Exception:
            log.exception("Failed to persist YOLO log")

        return jsonify(
            {
                "success": True,
                "message": "分割完成",
                "image": "data:image/png;base64,{}".format(base64_image),
                "detections": result["detections"],
                "original_shape": result["original_shape"],
                "has_segmentation": result["has_segmentation"],
                "object_count": result["object_count"],
                "processing_time": processing_time,
                "timestamp": time.time(),
                "image_type": "transparent_png",
            }
        )

    except Exception as e:
        log.exception("Request failed")
        return jsonify(
            {
                "success": False,
                "error": "处理过程中发生错误: {}".format(e),
                "processing_time": round(time.time() - start_time, 2),
            }
        ), 500


@app.route("/get_image/<path:filename>", methods=["GET"])
def get_image(filename):
    # send_from_directory rejects traversal attempts.
    return send_from_directory(DATA_DIR, filename)


@app.route("/health", methods=["GET"])
def health_check():
    """Liveness plus live saturation, so capacity decisions have real inputs.

    The `concurrency` block is the configured ceiling; `live` is what is
    actually happening right now (queue depth, rejections, pool contention).
    """
    return jsonify(
        {
            "status": "healthy",
            "model_loaded": model is not None,
            "model_classes": len(model.names) if model else 0,
            "uptime_seconds": round(time.time() - _STARTED_AT, 1),
            "concurrency": {
                "server_threads": SERVER_THREADS,
                "yolo_max_concurrency": MAX_YOLO_CONCURRENCY,
                "yolo_queue_timeout_s": YOLO_QUEUE_TIMEOUT,
                "yolo_max_waiters": YOLO_MAX_WAITERS,
                "db_pool_size": DB_POOL_SIZE,
                "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
                "gpt_rate_limit_per_minute": GPT_RATE_LIMIT_PER_MINUTE,
            },
            "live": {
                "yolo": _yolo_gate.snapshot(),
                "db_pool": {
                    "size": DB_POOL_SIZE,
                    "contention_total": _metrics.get("db_pool_contention"),
                    "exhausted_total": _metrics.get("db_pool_exhausted"),
                },
                "rate_limiter": _general_limiter.snapshot(),
                "gpt_rate_limiter": _gpt_limiter.snapshot(),
                "counters": _metrics.snapshot(),
            },
            "timestamp": time.time(),
        }
    )


@app.route("/ready", methods=["GET"])
def readiness_check():
    """Readiness probe: 200 only when this instance can actually serve traffic.

    Kept separate from /health so a load balancer can stop routing to an
    instance whose model or database is unavailable, instead of sending it
    requests that can only fail.
    """
    checks = {"model_loaded": model is not None}
    try:
        _fetch_one("SELECT 1 AS ok")
        checks["database"] = True
    except Exception as exc:  # noqa: BLE001 - any DB failure means "not ready"
        checks["database"] = False
        checks["database_error"] = str(exc)

    ready = all(checks.values())
    if not ready:
        log.warning("Readiness check failed: %s", checks)
    return jsonify({"ready": ready, "checks": checks, "timestamp": time.time()}), (
        200 if ready else 503
    )


@app.route("/model_info", methods=["GET"])
def model_info():
    return jsonify(
        {
            "model_name": os.path.basename(MODEL_PATH),
            "classes": model.names,
            "class_count": len(model.names),
            "success": True,
        }
    )


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"success": False, "error": "文件太大"}), 413


@app.errorhandler(500)
def internal_error(_e):
    return jsonify({"success": False, "error": "内部服务器错误"}), 500


@app.errorhandler(PoolExhausted)
def pool_exhausted(_e):
    """Transient: the caller should retry once a connection frees up."""
    response = jsonify({"success": False, "error": "服务繁忙，请稍后重试"})
    response.status_code = 503
    response.headers["Retry-After"] = "5"
    return response


@app.before_request
def _record_request():
    _metrics.inc("requests_total")
    endpoint = request.endpoint or "unknown"
    _metrics.inc("requests_by_endpoint." + endpoint)


@app.after_request
def _apply_cors(response):
    """Add CORS headers when CORS_ALLOW_ORIGINS opts in.

    Off by default: the desktop and native clients are not browsers, and an
    open policy on a LAN-exposed backend would let any web page on the network
    call it with the user's session token.
    """
    if not CORS_ALLOW_ORIGINS:
        return response

    origin = request.headers.get("Origin")
    if not origin:
        return response
    wildcard = "*" in CORS_ALLOW_ORIGINS
    if not wildcard and origin not in CORS_ALLOW_ORIGINS:
        return response

    response.headers["Access-Control-Allow-Origin"] = "*" if wildcard else origin
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Max-Age"] = "600"
    if not wildcard:
        # The response varies by origin, so caches must not share it.
        response.headers.add("Vary", "Origin")
    return response


@app.route("/submit_content", methods=["POST"])
@rate_limited(_general_limiter)
def submit_content():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "No JSON data received"}), 400

        try:
            response = get_http_session().post(OLLAMA_URL, json=data, timeout=OLLAMA_TIMEOUT)
        except requests.exceptions.ConnectionError:
            log.error("Cannot reach Ollama at %s", OLLAMA_URL)
            return jsonify(
                {"status": "error", "message": "Cannot connect to target API."}
            ), 503
        except requests.exceptions.Timeout:
            return jsonify({"status": "error", "message": "Target API timed out."}), 504

        if response.status_code != 200:
            log.error("Ollama error %s: %s", response.status_code, response.text[:200])
            return jsonify(
                {
                    "status": "error",
                    "message": "Target API returned error: {}".format(response.status_code),
                    "error_details": response.text,
                }
            ), response.status_code

        return jsonify({"status": "success", "api_response": response.json()}), 200

    except Exception as e:
        log.exception("submit_content failed")
        return jsonify({"error": str(e)}), 500


@app.route("/makeGPT", methods=["POST"])
@rate_limited(_gpt_limiter)
def make_gpt():
    temp_file_path = None
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON数据接收"}), 400

        image_base64 = data.get("image")
        prompt = data.get("prompt")
        if not image_base64:
            return jsonify({"success": False, "error": "没有接收到图片数据"}), 400
        if not prompt:
            return jsonify({"success": False, "error": "没有接收到提示词"}), 400

        log.info("makeGPT prompt=%r image_len=%d", prompt, len(image_base64))

        temp_file_path = base64_to_temp_file(image_base64)

        response = get_openai_client().images.edit(
            model="gpt-image-1",
            image=open(temp_file_path, "rb"),
            prompt=prompt,
            size="1024x1024",
        )

        if not getattr(response, "data", None):
            return jsonify({"success": False, "error": "API响应中没有图像数据"}), 500

        image_base64_out = response.data[0].b64_json

        try:
            user_bytes, _ = _strip_data_url(image_base64)
            user_path = save_image_bytes(user_bytes, "gpt_input")
            output_path = save_image_bytes(base64.b64decode(image_base64_out), "gpt_output")
            insert_gpt_log(prompt=prompt, user_image_path=user_path, output_image_path=output_path)
        except Exception:
            log.exception("Failed to persist GPT log")

        return jsonify({"success": True, "image": image_base64_out})

    except Exception as e:
        log.exception("makeGPT failed")
        return jsonify({"success": False, "error": "处理失败: {}".format(e)}), 500
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                log.warning("Could not delete temp file %s", temp_file_path)


# ============================================================================
# Auth / membership / admin
# ============================================================================


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _fetch_one(sql, params=()):
    conn = _get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def _fetch_all(sql, params=()):
    conn = _get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def _execute(sql, params=()) -> int:
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def _membership_state(row) -> dict:
    """Effective membership: expired subscriptions count as free."""
    expires = row.get("membership_expires_at")
    active = bool(expires) and expires > _utcnow().replace(tzinfo=None)
    tier = row.get("membership_tier", "free") if active else "free"
    return {
        "tier": tier,
        "expires_at": _iso(expires) if active else None,
        "active": active and tier != "free",
    }


def _user_public(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "membership": _membership_state(row),
        "created_at": _iso(row.get("created_at")),
    }


def _get_user(user_id: int):
    row = _fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
    return _user_public(row) if row else None


def _require_user():
    """Return (user, None) or (None, (response, status))."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify({"success": False, "error": "Not logged in"}), 401)
    uid = auth_utils.parse_token(auth[7:], AUTH_SECRET)
    if uid is None:
        return None, (jsonify({"success": False, "error": "Invalid or expired session"}), 401)
    user = _get_user(uid)
    if user is None:
        return None, (jsonify({"success": False, "error": "User no longer exists"}), 401)
    return user, None


def _require_admin():
    user, err = _require_user()
    if err is not None:
        return None, err
    if user["role"] != "admin":
        return None, (jsonify({"success": False, "error": "Admin access required"}), 403)
    return user, None


@app.route("/auth/register", methods=["POST"])
@rate_limited(_auth_limiter)
def auth_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    error = auth_utils.validate_credentials(username, password)
    if error:
        return jsonify({"success": False, "error": error}), 400

    existing = _fetch_one("SELECT id FROM users WHERE username = %s", (username,))
    if existing:
        return jsonify({"success": False, "error": "The username is already taken"}), 409

    # Bootstrap: the first registered user becomes the admin.
    is_first = _fetch_one("SELECT COUNT(*) AS n FROM users")["n"] == 0
    role = "admin" if is_first else "user"

    _execute(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        (username, auth_utils.hash_password(password), role),
    )
    user = _get_user(_fetch_one("SELECT id FROM users WHERE username = %s", (username,))["id"])
    log.info("Registered user %r (role=%s)", username, role)
    return jsonify(
        {
            "success": True,
            "token": auth_utils.make_token(user["id"], AUTH_SECRET),
            "user": user,
        }
    ), 201


@app.route("/auth/login", methods=["POST"])
@rate_limited(_auth_limiter)
def auth_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    row = _fetch_one("SELECT * FROM users WHERE username = %s", (username,))
    if row is None or not auth_utils.verify_password(password, row["password_hash"]):
        log.warning("Failed login for %r from %s", username, request.remote_addr)
        return jsonify({"success": False, "error": "Incorrect username or password"}), 401

    user = _user_public(row)
    log.info("User %r logged in", username)
    return jsonify(
        {
            "success": True,
            "token": auth_utils.make_token(user["id"], AUTH_SECRET),
            "user": user,
        }
    )


@app.route("/auth/me", methods=["GET"])
@rate_limited(_general_limiter)
def auth_me():
    user, err = _require_user()
    if err is not None:
        return err
    return jsonify({"success": True, "user": user})


@app.route("/membership/tiers", methods=["GET"])
def membership_tiers():
    return jsonify({"success": True, "tiers": MEMBERSHIP_TIERS})


@app.route("/membership/purchase", methods=["POST"])
@rate_limited(_general_limiter)
def membership_purchase():
    user, err = _require_user()
    if err is not None:
        return err

    data = request.get_json(silent=True) or {}
    tier_code = data.get("tier")
    tier = TIER_BY_CODE.get(tier_code)
    if tier is None or tier["code"] == "free":
        return jsonify({"success": False, "error": "Unknown membership tier"}), 400

    # Demo checkout: record the order as paid immediately.
    now = _utcnow().replace(tzinfo=None)
    current = _membership_state(
        _fetch_one("SELECT * FROM users WHERE id = %s", (user["id"],))
    )
    if current["active"] and current["tier"] == tier["code"] and current["expires_at"]:
        base = datetime.fromisoformat(current["expires_at"]).replace(tzinfo=None)
    else:
        base = now
    expires = base + timedelta(days=tier["days"])

    _execute(
        "INSERT INTO membership_orders (user_id, tier, price, status, expires_at)"
        " VALUES (%s, %s, %s, 'paid', %s)",
        (user["id"], tier["code"], tier["price"], expires),
    )
    _execute(
        "UPDATE users SET membership_tier = %s, membership_expires_at = %s WHERE id = %s",
        (tier["code"], expires, user["id"]),
    )
    log.info("User %s purchased %s (demo checkout)", user["username"], tier["code"])
    return jsonify({"success": True, "user": _get_user(user["id"])})


@app.route("/membership/me", methods=["GET"])
@rate_limited(_general_limiter)
def membership_me():
    user, err = _require_user()
    if err is not None:
        return err
    orders = _fetch_all(
        "SELECT id, tier, price, status, expires_at, created_at FROM membership_orders"
        " WHERE user_id = %s ORDER BY created_at DESC LIMIT 50",
        (user["id"],),
    )
    for order in orders:
        order["expires_at"] = _iso(order.get("expires_at"))
        order["created_at"] = _iso(order.get("created_at"))
        if hasattr(order.get("price"), "quantize"):
            order["price"] = float(order["price"])
    return jsonify({"success": True, "user": user, "orders": orders})


@app.route("/admin/stats", methods=["GET"])
@rate_limited(_general_limiter)
def admin_stats():
    _, err = _require_admin()
    if err is not None:
        return err

    def _count(sql, params=()):
        return _fetch_one(sql, params)["n"]

    revenue_row = _fetch_one("SELECT COALESCE(SUM(price), 0) AS total FROM membership_orders")
    paying = _count(
        "SELECT COUNT(*) AS n FROM users WHERE membership_tier != 'free'"
        " AND membership_expires_at > %s",
        (_utcnow().replace(tzinfo=None),),
    )
    stats = {
        "users": _count("SELECT COUNT(*) AS n FROM users"),
        "paying_members": paying,
        "orders": _count("SELECT COUNT(*) AS n FROM membership_orders"),
        "revenue": float(revenue_row["total"]),
        "gpt_requests": _count("SELECT COUNT(*) AS n FROM gpt_image_logs"),
        "yolo_requests": _count("SELECT COUNT(*) AS n FROM yolo_logs"),
    }
    recent = _fetch_all(
        "SELECT id, username, role, membership_tier, created_at FROM users"
        " ORDER BY created_at DESC LIMIT 5"
    )
    for row in recent:
        row["created_at"] = _iso(row.get("created_at"))
    return jsonify({"success": True, "stats": stats, "recent_users": recent})


@app.route("/admin/users", methods=["GET"])
@rate_limited(_general_limiter)
def admin_users():
    _, err = _require_admin()
    if err is not None:
        return err
    query = (request.args.get("query") or "").strip()
    if query:
        rows = _fetch_all(
            "SELECT * FROM users WHERE username LIKE %s ORDER BY created_at DESC LIMIT 200",
            (f"%{query}%",),
        )
    else:
        rows = _fetch_all("SELECT * FROM users ORDER BY created_at DESC LIMIT 200")
    return jsonify({"success": True, "users": [_user_public(r) for r in rows]})


@app.route("/admin/users/<int:user_id>", methods=["POST"])
@rate_limited(_general_limiter)
def admin_update_user(user_id: int):
    admin, err = _require_admin()
    if err is not None:
        return err

    target = _fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
    if target is None:
        return jsonify({"success": False, "error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    role = data.get("role")
    tier = data.get("tier")
    extend_days = data.get("extend_days")

    if role is not None:
        if role not in ("user", "admin"):
            return jsonify({"success": False, "error": "Invalid role"}), 400
        if target["id"] == admin["id"] and role != admin["role"]:
            return jsonify({"success": False, "error": "Cannot change your own role"}), 400
        _execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))

    if tier is not None:
        if tier not in TIER_BY_CODE:
            return jsonify({"success": False, "error": "Invalid tier"}), 400
        if tier == "free":
            _execute(
                "UPDATE users SET membership_tier = 'free', membership_expires_at = NULL"
                " WHERE id = %s",
                (user_id,),
            )
        else:
            expires = _utcnow().replace(tzinfo=None) + timedelta(days=TIER_BY_CODE[tier]["days"])
            _execute(
                "UPDATE users SET membership_tier = %s, membership_expires_at = %s WHERE id = %s",
                (tier, expires, user_id),
            )

    if extend_days is not None:
        try:
            days = int(extend_days)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "extend_days must be an integer"}), 400
        row = _fetch_one("SELECT membership_expires_at FROM users WHERE id = %s", (user_id,))
        base = row["membership_expires_at"]
        if base and base > _utcnow().replace(tzinfo=None):
            expires = base + timedelta(days=days)
        else:
            expires = _utcnow().replace(tzinfo=None) + timedelta(days=max(days, 0))
        _execute(
            "UPDATE users SET membership_tier = %s, membership_expires_at = %s WHERE id = %s",
            ("free" if expires <= _utcnow().replace(tzinfo=None) else target["membership_tier"], expires, user_id),
        )

    log.info(
        "Admin %s updated user %s (role=%s tier=%s extend=%s)",
        admin["username"], target["username"], role, tier, extend_days,
    )
    return jsonify({"success": True, "user": _get_user(user_id)})


@app.route("/admin/logs", methods=["GET"])
@rate_limited(_general_limiter)
def admin_logs():
    _, err = _require_admin()
    if err is not None:
        return err
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    except ValueError:
        limit = 50

    gpt = _fetch_all(
        "SELECT 'gpt' AS kind, g.id, NULL AS username, g.prompt AS detail, g.created_at"
        " FROM gpt_image_logs g ORDER BY g.created_at DESC LIMIT %s",
        (limit,),
    )
    yolo = _fetch_all(
        "SELECT 'yolo' AS kind, y.id, NULL AS username, y.object_count AS detail,"
        " y.created_at FROM yolo_logs y ORDER BY y.created_at DESC LIMIT %s",
        (limit,),
    )
    merged = sorted(gpt + yolo, key=lambda r: r["created_at"] or _utcnow(), reverse=True)[:limit]
    for row in merged:
        row["created_at"] = _iso(row.get("created_at"))
    return jsonify({"success": True, "logs": merged})


def _image_cleanup_loop(stop_event: threading.Event) -> None:
    while True:
        try:
            summary = retention_utils.prune_files(
                DATA_DIR,
                max_age_seconds=IMAGE_RETENTION_DAYS * 86400,
                max_files=IMAGE_MAX_FILES,
            )
        except Exception:
            log.exception("Image cleanup failed")
        else:
            if summary["removed"]:
                log.info(
                    "Image cleanup removed %d file(s), freed %.1f MiB, kept %d",
                    summary["removed"],
                    summary["freed_bytes"] / 1048576.0,
                    summary["kept"],
                )
        if stop_event.wait(IMAGE_CLEANUP_INTERVAL_S):
            return


def start_image_cleanup() -> threading.Thread:
    """Prune data/images on a daemon timer so the disk cannot fill up.

    Runs once at startup (to clean up after downtime) and then every
    IMAGE_CLEANUP_INTERVAL_S. Daemon so it never blocks interpreter exit.
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_image_cleanup_loop,
        args=(stop_event,),
        name="image-cleanup",
        daemon=True,
    )
    thread.start()
    return thread


if __name__ == "__main__":
    ensure_database_and_tables()
    start_image_cleanup()

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    log.info(
        "ReScene backend listening on http://%s:%d (threads=%d, yolo_concurrency=%d"
        " max_waiters=%d, rate_limit=%d/min, gpt_rate_limit=%d/min, db_pool=%d,"
        " image_retention=%dd/%d files, cors=%s)",
        host,
        port,
        SERVER_THREADS,
        MAX_YOLO_CONCURRENCY,
        YOLO_MAX_WAITERS,
        RATE_LIMIT_PER_MINUTE,
        GPT_RATE_LIMIT_PER_MINUTE,
        DB_POOL_SIZE,
        int(IMAGE_RETENTION_DAYS),
        IMAGE_MAX_FILES,
        ",".join(CORS_ALLOW_ORIGINS) if CORS_ALLOW_ORIGINS else "off",
    )
    try:
        from waitress import serve
    except ImportError:
        log.warning("waitress not installed; falling back to the Flask dev server")
        app.run(host=host, port=port, debug=False)
    else:
        serve(
            app,
            host=host,
            port=port,
            threads=SERVER_THREADS,
            connection_limit=int(os.getenv("CONNECTION_LIMIT", "100")),
            channel_timeout=int(os.getenv("CHANNEL_TIMEOUT", "120")),
        )
