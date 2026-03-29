import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt


def _pbkdf2(password: str, salt_hex: str, iterations: int) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return digest.hex()


def hash_password(password: str) -> str:
    iterations = 210000
    salt_hex = secrets.token_hex(16)
    digest_hex = _pbkdf2(password, salt_hex, iterations)
    return f"pbkdf2_sha256${iterations}${salt_hex}${digest_hex}"


def verify_password(plain_password: str, encoded_hash: str) -> bool:
    try:
        algo, iterations_str, salt_hex, digest_hex = encoded_hash.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    recalculated = _pbkdf2(plain_password, salt_hex, int(iterations_str))
    return hmac.compare_digest(recalculated, digest_hex)


def build_access_token(claims: dict) -> str:
    secret = os.getenv("AUTH_JWT_SECRET", "change-me")
    ttl_minutes = int(os.getenv("AUTH_TOKEN_TTL_MINUTES", "120"))
    now = datetime.now(timezone.utc)
    payload = {
        **claims,
        "iss": os.getenv("AUTH_ISSUER", "https://auth.nestra.homelabdev.space"),
        "aud": "nestra-api",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        "auth_mode": "alpha_demo",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    secret = os.getenv("AUTH_JWT_SECRET", "change-me")
    return jwt.decode(token, secret, algorithms=["HS256"], audience="nestra-api")
