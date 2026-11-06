"""Allow required local save effects to share one atomic transaction."""
from contextlib import contextmanager, closing
from .database import get_db


@contextmanager
def transaction(connection=None):
    if connection is not None:
        yield connection
    else:
        with closing(get_db()) as conn, conn:
            yield conn
