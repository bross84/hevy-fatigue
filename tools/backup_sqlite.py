"""Consistent SQLite backup including committed WAL content; never overwrite.

python tools/backup_sqlite.py /source/rackbook.db /backup/rackbook.db
"""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3


def backup(source, destination):
    source=Path(source).resolve(strict=True); destination=Path(destination).resolve()
    if source==destination: raise ValueError('Source and backup must be different files')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Reserve the output exclusively: accidentally repeating a command cannot
    # overwrite an earlier backup or a database containing newer workouts.
    fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise RuntimeError('Backup integrity check failed; do not use this output')
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('destination')
    args=parser.parse_args();print(backup(args.source,args.destination))
