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

import mysql.connector
import mysql.connector.pooling
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI
from PIL import Image

import cv2
import numpy as np

from concurrency_utils import SlidingWindowRateLimiter, lazy_singleton

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
# Local-only desktop backend: 16 MiB upload cap, no CORS (the Flutter desktop
# client is not subject to browser same-origin rules).
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def rate_limited(limiter):
    """Reject requests over the per-IP limit with 429 + Retry-After."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = request.remote_addr or "unknown"
            if not limiter.allow(key):
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
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
GPT_RATE_LIMIT_PER_MINUTE = int(os.getenv("GPT_RATE_LIMIT_PER_MINUTE", "10"))

# ultralytics inference is not guaranteed thread-safe; a semaphore keeps at
# most MAX_YOLO_CONCURRENCY predictions in flight (default: serialized).
_yolo_semaphore = threading.Semaphore(MAX_YOLO_CONCURRENCY)

# Per-client-IP sliding window limiters; /makeGPT gets a much stricter cap
# to protect the OpenAI quota.
_general_limiter = SlidingWindowRateLimiter(RATE_LIMIT_PER_MINUTE, window_seconds=60.0)
_gpt_limiter = SlidingWindowRateLimiter(GPT_RATE_LIMIT_PER_MINUTE, window_seconds=60.0)

# Keep-alive session for the Ollama proxy.
_http_session = requests.Session()

# OpenAI client is created lazily so the server can start without an API key.
get_openai_client = lazy_singleton(lambda: OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

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


def _insert_log(sql, params):
    """Insert a log row; failures are logged but never fail the HTTP request."""
    conn = cursor = None
    try:
        conn = connection_pool.get_connection()
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
        raw, _ = _strip_data_url(image_data)

        nparr = np.frombuffer(raw, np.uint8)
        orig_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if orig_img is None:
            raise ValueError("无法解码图片")

        if not _yolo_semaphore.acquire(timeout=YOLO_QUEUE_TIMEOUT):
            return {
                "success": False,
                "error": "服务器繁忙，请稍后重试",
                "retry_after": 30,
            }
        try:
            results = model.predict(orig_img, save=False, conf=0.25, iou=0.45, verbose=False)
        finally:
            _yolo_semaphore.release()
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
    return jsonify(
        {
            "status": "healthy",
            "model_loaded": model is not None,
            "model_classes": len(model.names) if model else 0,
            "concurrency": {
                "server_threads": SERVER_THREADS,
                "yolo_max_concurrency": MAX_YOLO_CONCURRENCY,
                "yolo_queue_timeout_s": YOLO_QUEUE_TIMEOUT,
                "db_pool_size": DB_POOL_SIZE,
                "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
                "gpt_rate_limit_per_minute": GPT_RATE_LIMIT_PER_MINUTE,
            },
            "timestamp": time.time(),
        }
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


@app.route("/submit_content", methods=["POST"])
@rate_limited(_general_limiter)
def submit_content():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "No JSON data received"}), 400

        try:
            response = _http_session.post(OLLAMA_URL, json=data, timeout=300)
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


if __name__ == "__main__":
    ensure_database_and_tables()

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    log.info(
        "ReScene backend listening on http://%s:%d (threads=%d, yolo_concurrency=%d,"
        " rate_limit=%d/min, gpt_rate_limit=%d/min, db_pool=%d)",
        host,
        port,
        SERVER_THREADS,
        MAX_YOLO_CONCURRENCY,
        RATE_LIMIT_PER_MINUTE,
        GPT_RATE_LIMIT_PER_MINUTE,
        DB_POOL_SIZE,
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
