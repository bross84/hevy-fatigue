"""Shared host credential storage and original legacy fallback behavior."""
import os
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from database import AppSetting, SessionLocal

# ── Encryption ────────────────────────────────────────────────────────────────
# A Fernet key is generated once and stored in the Docker volume at /data/app.key.
# The API key in the DB is encrypted with it, so a DB dump alone can't expose it.
_FERNET_KEY_PATH = os.getenv("FERNET_KEY_PATH", "/data/app.key")
_fernet: Fernet | None = None

def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    if os.path.exists(_FERNET_KEY_PATH):
        with open(_FERNET_KEY_PATH, "rb") as f:
            key = f.read().strip()
    else:
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
