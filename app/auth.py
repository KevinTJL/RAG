from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.profile_store import safe_user_id


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def now_ts() -> int:
    return int(time.time())


def normalize_email(email: str) -> str:
    return email.strip().lower()


def password_hash(password: str, salt: str | None = None) -> str:
    salt_bytes = b64url_decode(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 260_000)
    return f"pbkdf2_sha256${b64url_encode(salt_bytes)}${b64url_encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, expected = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    return hmac.compare_digest(password_hash(password, salt), stored)


def sign_payload(payload: dict[str, Any]) -> str:
    body = b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = hmac.new(settings.auth_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{b64url_encode(signature)}"


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(settings.auth_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(b64url_encode(expected), signature):
        return None
    try:
        payload = json.loads(b64url_decode(body).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp", 0) or 0) < now_ts():
        return None
    return payload if isinstance(payload, dict) else None


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str


class AuthStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.project_root / "db" / "users.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"users": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}}
        return data if isinstance(data, dict) else {"users": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.path.chmod(0o600)

    def create_user(self, email: str, password: str) -> AuthUser:
        normalized_email = normalize_email(email)
        if not normalized_email or "@" not in normalized_email:
            raise ValueError("请输入有效邮箱")
        if len(password) < 8:
            raise ValueError("密码至少需要 8 位")

        data = self._load()
        users = data.setdefault("users", {})
        if normalized_email in users:
            raise ValueError("该邮箱已注册")

        user_id = safe_user_id(f"user-{secrets.token_urlsafe(8)}")
        users[normalized_email] = {
            "id": user_id,
            "email": normalized_email,
            "password_hash": password_hash(password),
            "created_at": now_ts(),
        }
        self._save(data)
        return AuthUser(id=user_id, email=normalized_email)

    def authenticate(self, email: str, password: str) -> AuthUser | None:
        normalized_email = normalize_email(email)
        user = self._load().get("users", {}).get(normalized_email)
        if not isinstance(user, dict):
            return None
        if not verify_password(password, str(user.get("password_hash", ""))):
            return None
        return AuthUser(id=str(user.get("id")), email=str(user.get("email")))

    def issue_token(self, user: AuthUser) -> str:
        exp = now_ts() + settings.auth_token_ttl_hours * 3600
        return sign_payload({"sub": user.id, "email": user.email, "exp": exp})

    def user_from_token(self, token: str) -> AuthUser | None:
        payload = verify_token(token)
        if not payload:
            return None
        return AuthUser(id=str(payload.get("sub", "")), email=str(payload.get("email", "")))
