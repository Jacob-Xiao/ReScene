"""Self-tests for backend auth primitives (auth_utils).

Pure stdlib — no Flask, MySQL, or YOLO required.

Run:  python test_auth.py
"""

import time
import unittest

import auth_utils

SECRET = "unit-test-secret"


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify_roundtrip(self):
        stored = auth_utils.hash_password("correct horse battery")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertTrue(auth_utils.verify_password("correct horse battery", stored))

    def test_wrong_password_rejected(self):
        stored = auth_utils.hash_password("correct horse battery")
        self.assertFalse(auth_utils.verify_password("wrong password", stored))

    def test_salts_are_random(self):
        self.assertNotEqual(
            auth_utils.hash_password("same"),
            auth_utils.hash_password("same"),
        )

    def test_malformed_stored_hash_rejected(self):
        self.assertFalse(auth_utils.verify_password("x", "not-a-valid-hash"))
        self.assertFalse(auth_utils.verify_password("x", "md5$abc$def"))
        self.assertFalse(auth_utils.verify_password("x", ""))


class ValidationTests(unittest.TestCase):
    def test_valid_credentials_pass(self):
        self.assertIsNone(auth_utils.validate_credentials("alice_01", "password123"))

    def test_short_username_rejected(self):
        self.assertIsNotNone(auth_utils.validate_credentials("ab", "password123"))

    def test_bad_username_chars_rejected(self):
        self.assertIsNotNone(auth_utils.validate_credentials("bad name!", "password123"))

    def test_short_password_rejected(self):
        self.assertIsNotNone(auth_utils.validate_credentials("alice", "short"))

    def test_none_inputs_rejected(self):
        self.assertIsNotNone(auth_utils.validate_credentials(None, None))


class TokenTests(unittest.TestCase):
    def test_roundtrip(self):
        token = auth_utils.make_token(42, SECRET)
        self.assertEqual(auth_utils.parse_token(token, SECRET), 42)

    def test_wrong_secret_rejected(self):
        token = auth_utils.make_token(42, SECRET)
        self.assertIsNone(auth_utils.parse_token(token, "other-secret"))

    def test_tampered_payload_rejected(self):
        token = auth_utils.make_token(42, SECRET)
        payload, sig = token.split(".")
        # Flip user id inside the base64 payload without re-signing.
        import base64
        import json

        data = json.loads(base64.urlsafe_b64decode(payload))
        data["uid"] = 43
        forged = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        self.assertIsNone(auth_utils.parse_token(f"{forged}.{sig}", SECRET))

    def test_expired_token_rejected(self):
        token = auth_utils.make_token(42, SECRET, ttl_seconds=-10)
        self.assertIsNone(auth_utils.parse_token(token, SECRET))

    def test_garbage_tokens_rejected(self):
        for bad in ("", "abc", "a.b", "....", None):
            self.assertIsNone(auth_utils.parse_token(bad, SECRET))

    def test_tokens_for_different_users_differ(self):
        self.assertNotEqual(
            auth_utils.make_token(1, SECRET),
            auth_utils.make_token(2, SECRET),
        )

    def test_uid_must_be_int(self):
        import base64
        import json

        payload = base64.urlsafe_b64encode(
            json.dumps({"uid": "one", "exp": int(time.time()) + 60}).encode()
        ).decode()
        import hashlib
        import hmac

        sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        self.assertIsNone(auth_utils.parse_token(f"{payload}.{sig}", SECRET))


if __name__ == "__main__":
    unittest.main(verbosity=2)
