"""Logging database configuration; never reassign the host DB_PATH."""
import os
from pathlib import Path
from contextvars import ContextVar

offline_database = ContextVar('rackbook_offline_database', default=None)


def database_path():
    return Path(offline_database.get() or os.environ.get('RACKBOOK_DB_PATH', './rackbook.db')).resolve()


def validate_database_paths(host_path=None):
    host = Path(host_path or os.environ.get('DB_PATH', './hevy_fatigue.db')).resolve()
    training = database_path()
    if host == training or (host.exists() and training.exists() and os.path.samefile(host, training)):
        raise RuntimeError('DB_PATH and RACKBOOK_DB_PATH must identify different SQLite files.')
