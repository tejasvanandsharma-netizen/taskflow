"""TaskFlow authentication: PBKDF2 password hashing and signed bearer tokens.

Uses only the Python standard library so the app keeps working with zero
external API keys (mirrors the Section 3 keyless-mock philosophy).
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

_PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days

_SECRET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_secret")

_bearer = HTTPBearer(auto_error=False)


def _load_secret() -> str:
    """Persist one random secret so tokens survive server restarts."""
    if os.path.exists(_SECRET_FILE):
        with open(_SECRET_FILE, "r", encoding="utf-8") as f:
            secret = f.read().strip()
        if secret:
            return secret
    secret = secrets.token_hex(32)
    with open(_SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(secret)
    return secret


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    """Return pbkdf2$iterations$salt$hash — constant-time verifiable."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), _PBKDF2_ITERATIONS
    )
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$", 3)
        if algo != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def create_token(user_id: int) -> str:
    """Signed token: base64url({uid, exp}) . sha256_hmac."""
    payload = _b64url(json.dumps({"uid": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS}).encode("utf-8"))
    signature = hmac.new(_load_secret().encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def create_reset_token(user_id: int, ttl_seconds: int = 900) -> str:
    """Short-lived signed token used for the forgot-password flow."""
    payload = _b64url(
        json.dumps({"uid": user_id, "exp": int(time.time()) + ttl_seconds, "pur": "reset"}).encode("utf-8")
    )
    signature = hmac.new(_load_secret().encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def decode_reset_token(token: str) -> int | None:
    """Return the user id if the reset token is valid, unexpired, and reset-scoped."""
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(
            _load_secret().encode("utf-8"), payload.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_unb64url(payload))
        if data.get("pur") != "reset":
            return None
        if int(data["exp"]) < time.time():
            return None
        return int(data["uid"])
    except (ValueError, KeyError, TypeError):
        return None


def decode_token(token: str) -> int | None:
    """Return the user id if the token is well-formed and unexpired."""
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(
            _load_secret().encode("utf-8"), payload.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_unb64url(payload))
        if int(data["exp"]) < time.time():
            return None
        return int(data["uid"])
    except (ValueError, KeyError, TypeError):
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: require a valid bearer token, return the user."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user, but returns None when no valid token is present."""
    if credentials is None:
        return None
    user_id = decode_token(credentials.credentials)
    if user_id is None:
        return None
    return db.get(User, user_id)
