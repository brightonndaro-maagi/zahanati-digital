from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from flask import current_app

from app.common.errors import APIError


def _fernet():
    keys = current_app.config.get("FILE_ENCRYPTION_KEYS") or []
    if not keys:
        raise APIError("File encryption is not configured on the server", 503)
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError):
        current_app.logger.error("FILE_ENCRYPTION_KEYS contains an invalid Fernet key")
        raise APIError("File encryption is misconfigured on the server", 503)


def encrypt(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    try:
        return _fernet().decrypt(token)
    except InvalidToken:
        current_app.logger.error("Stored file could not be decrypted (wrong key or corrupted file)")
        raise APIError("The stored file could not be read", 500)
