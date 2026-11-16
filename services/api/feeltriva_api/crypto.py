"""Field encryption for session free text (Fernet: AES-128-CBC + HMAC-SHA256)."""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet

from .settings import Settings

log = logging.getLogger(__name__)
_DEV_SEED = b"feeltriva-local-development-only-not-a-secret"


class FieldCipher:
    def __init__(self, settings: Settings) -> None:
        key = settings.session_encryption_key
        if not key:
            if not settings.is_local:  # also enforced by Settings
                raise RuntimeError("SESSION_ENCRYPTION_KEY is required")
            log.warning("SESSION_ENCRYPTION_KEY unset: using the built-in development key (not secret)")
            key = base64.urlsafe_b64encode(hashlib.sha256(_DEV_SEED).digest()).decode()
        self._fernet = Fernet(key)

    def encrypt(self, text: str) -> bytes:
        return self._fernet.encrypt(text.encode("utf-8"))

    def decrypt(self, token: bytes) -> str:
        return self._fernet.decrypt(bytes(token)).decode("utf-8")
