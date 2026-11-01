"""Kimlik bilgilerinin yerelde şifreli saklanması (Fernet / AES-128-CBC + HMAC)."""
from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import KEY_PATH


def _load_key() -> bytes:
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes().strip()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key


_fernet = Fernet(_load_key())


def encrypt(data: dict[str, Any]) -> str:
    return _fernet.encrypt(json.dumps(data).encode()).decode()


def decrypt(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    try:
        return json.loads(_fernet.decrypt(token.encode()).decode())
    except (InvalidToken, ValueError):
        return {}


def mask(value: str) -> str:
    """Arayüze gönderilen gizli değerleri maskeler."""
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return value[:3] + "••••" + value[-3:]
