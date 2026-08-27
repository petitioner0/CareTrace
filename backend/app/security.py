from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User


bearer = HTTPBearer(auto_error=False)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or hashlib.sha256(b"caretrace-demo-salt").digest()[:16]
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, salt, expected = encoded.split("$", 2)
        actual = hash_password(password, _unb64(salt)).split("$", 2)[2]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def issue_token(user: User, ttl_seconds: int = 8 * 60 * 60) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(
        json.dumps(
            {
                "sub": user.id,
                "clinic_id": user.clinic_id,
                "role": user.role,
                "patient_id": user.patient_id,
                "exp": int(time.time()) + ttl_seconds,
            },
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = hmac.new(settings.app_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(signature)}"


def decode_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}"
        expected = hmac.new(settings.app_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(signature), expected):
            raise ValueError("signature")
        data = json.loads(_unb64(payload))
        if int(data["exp"]) < int(time.time()):
            raise ValueError("expired")
        return data
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@dataclass
class Principal:
    id: str
    clinic_id: str
    role: str
    patient_id: str | None
    display_name: str


def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    claims = decode_token(credentials.credentials)
    user = db.scalar(select(User).where(User.id == claims["sub"], User.clinic_id == claims["clinic_id"]))
    if not user or user.role != claims["role"]:
        raise HTTPException(status_code=401, detail="Account no longer valid")
    return Principal(user.id, user.clinic_id, user.role, user.patient_id, user.display_name)


def require_roles(*roles: str):
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=403, detail="Role is not permitted for this operation")
        return principal

    return dependency


class FieldCipher:
    def __init__(self) -> None:
        self._fernet = Fernet(settings.fernet_key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Encrypted field cannot be decrypted with the configured key") from exc


cipher = FieldCipher()

