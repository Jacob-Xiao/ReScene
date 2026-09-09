"""Authentication primitives for the ReScene backend.

Pure stdlib (pbkdf2 + HMAC tokens) so the logic is unit-testable without
Flask, MySQL, or YOLO. Tokens are HMAC-signed payloads carrying uid + expiry.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import time

PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 7 * 24 * 3600
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
MIN_PASSWORD_LENGTH = 8


def validate_credentials(username: str, password: str) -> str | None:
    """Return an error message for invalid input, or None when valid."""
    if not USERNAME_RE.match(username or ""):
        return "用户名需为 3-32 位字母/数字/下划线"
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"密码至少 {MIN_PASSWORD_LENGTH} 个字符"
    return None


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt if salt is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}".format(
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest, expected)


def make_token(user_id: int, secret: str, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"uid": int(user_id), "exp": int(time.time()) + int(ttl_seconds)}).encode("utf-8")
    ).decode("ascii")
    signature = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def parse_token(token: str, secret: str) -> int | None:
    """Return the user id for a valid, unexpired token; None otherwise."""
    try:
        payload, signature = token.split(".")
    except (ValueError, AttributeError):
        return None
    expected = hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        if not isinstance(data.get("uid"), int):
            return None
        if int(data.get("exp", 0)) < time.time():
            return None
        return data["uid"]
    except (ValueError, TypeError, KeyError):
        return None
