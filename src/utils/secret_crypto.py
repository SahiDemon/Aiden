from __future__ import annotations

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class SecretCryptoError(Exception):
    pass


def _derive_fernet_key(master_key: str) -> bytes:
    digest = hashlib.sha256(master_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet(master_key: Optional[str]) -> Fernet:
    if not master_key:
        raise SecretCryptoError("SETTINGS_ENCRYPTION_KEY is not configured.")
    return Fernet(_derive_fernet_key(master_key))


def encrypt_value(master_key: str, value: str) -> str:
    if value == "":
        return ""
    return get_fernet(master_key).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(master_key: str, value: str) -> str:
    if value == "":
        return ""
    try:
        return get_fernet(master_key).decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretCryptoError("Failed to decrypt stored secret.") from exc
