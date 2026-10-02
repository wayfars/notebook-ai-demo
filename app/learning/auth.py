"""Password, session, and CSRF helpers for the learning API."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from . import store

SESSION_COOKIE = "learn_session"
SESSION_HOURS = 12


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        raise ValueError("password must be 12 to 1024 characters")
    salt = secrets.token_bytes(16)
    result = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${result.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(rounds) < 100_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def create_session(user_id: int) -> tuple[str, str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)).isoformat()
    with store.db() as conn:
        conn.execute("DELETE FROM learn_sessions WHERE expires_at < ?", (datetime.now(timezone.utc).isoformat(),))
        conn.execute("INSERT INTO learn_sessions(token_hash,user_id,csrf_hash,csrf_token,expires_at) VALUES(?,?,?,?,?)",
                     (_digest(token), user_id, _digest(csrf), csrf, expires))
    return token, csrf, expires


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "authentication required")
    with store.db() as conn:
        row = conn.execute("""SELECT u.*,s.csrf_hash,s.csrf_token,s.expires_at FROM learn_sessions s
          JOIN learn_users u ON u.id=s.user_id WHERE s.token_hash=?""", (_digest(token),)).fetchone()
    if not row or datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(401, "session expired")
    return dict(row)


def require_csrf(request: Request, user):
    token = request.headers.get("X-CSRF-Token", "")
    if not token or not hmac.compare_digest(_digest(token), user["csrf_hash"]):
        raise HTTPException(403, "valid CSRF token required")


def clear_session(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with store.db() as conn:
            conn.execute("DELETE FROM learn_sessions WHERE token_hash=?", (_digest(token),))
