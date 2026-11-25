"""Encrypted file storage on local disk. Files are named by random keys, never by user input."""
import os
import uuid
from pathlib import Path

from flask import current_app

from app.common import crypto


def _root():
    root = Path(current_app.config["UPLOAD_DIR"])
    if not root.is_absolute():
        root = Path(current_app.root_path).parent / root
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def _path(key):
    if not key or "/" in key or "\\" in key or ".." in key:
        raise ValueError("invalid storage key")
    return _root() / key


def save_encrypted(data: bytes) -> str:
    token = crypto.encrypt(data)  # fail before touching the disk if encryption is not configured
    key = f"{uuid.uuid4().hex}.enc"
    path = _path(key)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(token)
    return key


def read_decrypted(key: str) -> bytes:
    return crypto.decrypt(_path(key).read_bytes())


def delete(key: str):
    try:
        _path(key).unlink()
    except FileNotFoundError:
        pass
