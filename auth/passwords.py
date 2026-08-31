"""使用 PBKDF2-HMAC-SHA256 安全存储和校验密码。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 310_000


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    if len(password) < 8:
        raise ValueError("密码长度至少为 8 位")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            ALGORITHM,
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded_hash.split("$", 3)
        if algorithm != ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(actual_digest, expected_digest)
