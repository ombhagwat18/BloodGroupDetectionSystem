"""Login, roles and signed tokens. Standard library only (PBKDF2 + HMAC), no extra packages."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query

from . import db

ROLES = ("admin", "doctor", "lab_tech", "operator")
TOKEN_TTL = 12 * 3600  # seconds
PBKDF2_ROUNDS = 200_000
MIN_PASSWORD = 8


def _secret() -> bytes:
    env = os.environ.get("HEMOSCAN_SECRET")
    if env:
        return env.encode()
    f = db.DATA_DIR / "secret.key"
    if not f.exists():
        db.DATA_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return "pbkdf2$%d$%s$%s" % (PBKDF2_ROUNDS, salt, dk.hex())


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, want = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(dk.hex(), want)
    except Exception:  # noqa: BLE001 - malformed hash means "no"
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: int) -> str:
    body = _b64(json.dumps({"uid": user_id, "exp": int(time.time()) + TOKEN_TTL}).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return body + "." + sig


def read_token(token: str) -> Optional[int]:
    """Returns the user id, or None when the token is malformed, tampered with or expired."""
    try:
        body, sig = token.split(".")
        want = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, want):
            return None
        data = json.loads(_unb64(body))
        return data["uid"] if data["exp"] > time.time() else None
    except Exception:  # noqa: BLE001
        return None


def public(u) -> dict:
    return {"id": u["id"], "username": u["username"], "full_name": u["full_name"], "role": u["role"],
            "active": bool(u["active"]), "created_at": u["created_at"], "last_login": u["last_login"]}


def user_from_token(token: Optional[str]):
    uid = read_token(token) if token else None
    if uid is None:
        return None
    with db.conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()
    return db.row(r)


def current_user(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    """Bearer header for fetch calls; ?token= only so <img src> can load scan images."""
    raw = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else token
    u = user_from_token(raw)
    if not u:
        raise HTTPException(401, "login required")
    return u


def require(*roles):
    """Dependency: signed-in user whose role is one of `roles` (any signed-in user if none given)."""
    def dep(u=Depends(current_user)):
        if roles and u["role"] not in roles:
            raise HTTPException(403, "your role (%s) is not allowed to do this" % u["role"])
        return u
    return dep


def user_count() -> int:
    with db.conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def active_admins(c) -> int:
    return c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
