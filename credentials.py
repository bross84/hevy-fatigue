"""Shared host credential storage and original legacy fallback behavior."""
import base64
import logging
import os
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session
from database import AppSetting, SessionLocal

# ── Encryption ────────────────────────────────────────────────────────────────
# A Fernet key is generated once and stored in the Docker volume at /data/app.key.
# The API key in the DB is encrypted with it, so a DB dump alone can't expose it.
_FERNET_KEY_PATH = os.getenv("FERNET_KEY_PATH", "/data/app.key")
_fernet: Fernet | None = None
_ENCRYPTED_SETTING_KEYS = ("hevy_api_key", "ai_api_key")
_log = logging.getLogger(__name__)


class StoredKeyUnreadable(InvalidToken):
    """A saved credential is encrypted, but not with the current key file."""


UNREADABLE_KEY_MESSAGE = (
    "The saved key can't be read with the current encryption key file. "
    "Restore the original key file, or save the key again."
)


def _looks_encrypted(value: str) -> bool:
    """True when value has the shape of a Fernet token (never legacy plaintext)."""
    try:
        raw = base64.urlsafe_b64decode(value.strip().encode())
    except (ValueError, TypeError):
        return False
    # version byte + timestamp + IV + at least one cipher block + HMAC
    return len(raw) >= 73 and raw[0] == 0x80


def _encrypted_settings_exist() -> bool:
    try:
        with SessionLocal() as db:
            rows = db.query(AppSetting.value).filter(AppSetting.key.in_(_ENCRYPTED_SETTING_KEYS)).all()
    except Exception:
        return False
    return any(value and _looks_encrypted(value) for (value,) in rows)


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    if os.path.exists(_FERNET_KEY_PATH):
        with open(_FERNET_KEY_PATH, "rb") as f:
            key = f.read().strip()
    else:
        if _encrypted_settings_exist():
            # Saved values stay untouched, so restoring the original file still recovers them.
            _log.warning("Encryption key file is missing but encrypted settings exist; "
                         "creating a new key file. Restore the original key file to read them.")
        key = Fernet.generate_key()
        os.makedirs(os.path.dirname(_FERNET_KEY_PATH), exist_ok=True)
        with open(_FERNET_KEY_PATH, "wb") as f:
            f.write(key)
        try:
            os.chmod(_FERNET_KEY_PATH, 0o600)
        except OSError:
            pass  # Windows doesn't support chmod — safe to ignore
    _fernet = Fernet(key)
    return _fernet

def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()

def _decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()
def get_db_api_key(db: Session) -> str | None:
    """Read and decrypt the Hevy API key stored in the app_settings table."""
    row = db.query(AppSetting).filter(AppSetting.key == "hevy_api_key").first()
    if not row or not row.value:
        return None
    try:
        return _decrypt(row.value)
    except Exception:
        if _looks_encrypted(row.value):
            # Encrypted with a different key file: never overwrite it, or the
            # original key file could no longer recover it.
            raise StoredKeyUnreadable(UNREADABLE_KEY_MESSAGE) from None
        # One-time compatibility migration from legacy plaintext storage.
        legacy_plaintext = row.value.strip()
        if not legacy_plaintext:
            return None
        row.value = _encrypt(legacy_plaintext)
        db.commit()
        return legacy_plaintext

def get_api_key():
    from hevy_client import _load_api_key
    with SessionLocal() as db:
        return get_db_api_key(db) or _load_api_key()


def save_api_key(raw_key):
    with SessionLocal() as db:
        row = db.query(AppSetting).filter_by(key='hevy_api_key').first()
        value = _encrypt(raw_key)
        if row:
            row.value = value
        else:
            db.add(AppSetting(key='hevy_api_key', value=value))
        db.commit()
