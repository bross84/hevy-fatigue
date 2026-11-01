"""Offline release verification on disposable copies; run with Docker --network none.

Inputs must be read-only mounts. Reports contain hashes/counts, never row values.
This is not an application preview and never makes a Hevy request.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile


EXPECTED = {
    'hevy-fatigue/hevy_fatigue.db': '96cfcc96c57f1586d2d6fc9bc9b254783ec44345214e97c686cfc0308836db3e',
    'rackbook/rackbook.db': 'dd262f59e3cb81da203378af58f2ff9cb54a99adcbdfa390d780288d9e1fc694',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(path, columns=None):
    with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro', uri=True)) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        result = {}
        for table in tables:
            quote = lambda name: '"'+name.replace('"', '""')+'"'
            names = [r[1] for r in db.execute('PRAGMA table_info('+quote(table)+')')]
            selected = columns[table]['columns'] if columns and table in columns else names
            rows = db.execute('SELECT '+','.join(map(quote, selected))+' FROM '+quote(table)).fetchall()
            hashes = Counter(hashlib.sha256(repr(row).encode()).hexdigest() for row in rows)
            result[table] = {'columns': selected, 'rows': hashes, 'count': len(rows),
                             'hash': hashlib.sha256(json.dumps(sorted(hashes.items())).encode()).hexdigest()}
        return result


def rpe_line_ending_change(original, migrated, candidate):
    """Approve only a proven LF/CRLF fingerprint change with identical table rows."""
    values = []
    others = []
    for path in (original, migrated):
        with closing(sqlite3.connect(Path(path).as_uri()+'?mode=ro', uri=True)) as db:
            row = db.execute('SELECT value FROM app_settings WHERE key=?', ('rpe_chart_source',)).fetchone()
            values.append(row[0] if row else None)
            others.append(sorted(db.execute('SELECT key,value FROM app_settings WHERE key<>?', ('rpe_chart_source',)).fetchall()))
    data = Path(candidate)/'rackbook/data'
    csv = data/'rpe_chart_user.csv'
    if not csv.exists():
        csv = data/'rpe_chart.csv'
    raw = csv.read_bytes()
    variants = {hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}
    return others[0] == others[1] and all(value in variants for value in values)


RUNNER = r'''
import json, os, socket
from datetime import date
from pathlib import Path
def blocked(*args, **kwargs):
    raise RuntimeError('Outbound network forbidden during production-copy verification')
socket.socket.connect = blocked
socket.create_connection = blocked
import main
from database import SessionLocal, engine
class FrozenDate(date):
    @classmethod
    def today(cls): return cls(2026,10,31)
main.date_type = FrozenDate
main.startup()
if os.environ['VERIFY_COMBINED'] == '1':
    main.startup()
    import credentials
    assert credentials.get_api_key(), 'Host credential unavailable'
with SessionLocal() as db:
    output = {}
    for day in (date(2026,10,30), date(2026,10,31), date(2026,11,1)):
        FrozenDate.today = classmethod(lambda cls, day=day: cls(day.year,day.month,day.day))
        output[str(day)] = {
            'training_load': main.get_training_load(days=60, db=db),
            'pattern_stress': main.get_pattern_stress(target_date=day, db=db),
        }
Path(os.environ['VERIFY_OUTPUT']).write_text(json.dumps(output, sort_keys=True, default=str, allow_nan=False))
engine.dispose()
'''


def run_app(code, folder, combined):
    env = {**os.environ, 'DB_PATH': str(folder/'host.db'),
           'RACKBOOK_DB_PATH': str(folder/'rack.db'),
           'HEVY_FATIGUE_DB_PATH': str(folder/'host.db'),
           'FERNET_KEY_PATH': str(folder/'app.key'),
           'HEVY_WRITES_ENABLED': '0', 'RACKBOOK_READ_ONLY_PREVIEW': '1',
           'HEVY_API_KEY': '', 'HEVY_API_KEY_FILE': str(folder/'absent'),
           'VERIFY_COMBINED': str(int(combined)), 'VERIFY_OUTPUT': str(folder/'outputs.json'),
           'PYTHONDONTWRITEBYTECODE': '1', 'TZ': 'America/New_York'}
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', RUNNER], cwd=code,
                            env=env, capture_output=True, text=True, timeout=180)
    # Keep diagnostics private; never echo app output which might include settings.
    (folder/'runtime.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError('Application verification failed; private runtime.log requires inspection')
    return json.loads((folder/'outputs.json').read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    output = Path(args.output).resolve()
    output.mkdir(exist_ok=False, parents=True)
    with tempfile.TemporaryDirectory(prefix='production-copy-') as temporary:
        root = Path(temporary)
        originals = root/'originals'
        with tarfile.open(args.archive) as archive:
            archive.extractall(originals, filter='data')
        sources = next(originals.iterdir())
        hashes = {name: digest(sources/name) for name in EXPECTED}
        assert hashes == EXPECTED, 'Downloaded database hash mismatch'
        baseline = root/'baseline-code'
        with tarfile.open(args.baseline) as archive:
            archive.extractall(baseline, filter='data')
        before = {name: snapshot(sources/name) for name in EXPECTED}
        runs = {}
        for name, combined in [('baseline', False), ('candidate', True)]:
            folder = output/name
            folder.mkdir()
            shutil.copyfile(sources/'hevy-fatigue/hevy_fatigue.db', folder/'host.db')
            shutil.copyfile(sources/'rackbook/rackbook.db', folder/'rack.db')
            shutil.copyfile(sources/'hevy-fatigue/app.key', folder/'app.key')
            runs[name] = run_app(Path(args.candidate) if combined else baseline, folder, combined)
        changes = {}
        preserved = True
        for source, filename in [('hevy-fatigue/hevy_fatigue.db', 'host.db'), ('rackbook/rackbook.db', 'rack.db')]:
            old = before[source]
            new = snapshot(output/'candidate'/filename, columns=old)
            changed = {}
            for table, state in old.items():
                current = new.get(table)
                missing = state['rows'] - current['rows'] if current else state['rows']
                added = current['rows'] - state['rows'] if current else Counter()
                if missing or added:
                    changed[table] = {'before': state['count'], 'after': current['count'] if current else 0,
                                      'missing_or_changed': sum(missing.values()), 'added': sum(added.values())}
                    approved = (source.startswith('rackbook/') and table == 'app_settings'
                                and old['rpe_chart']['rows'] == new['rpe_chart']['rows']
                                and rpe_line_ending_change(sources/source, output/'candidate'/filename, args.candidate))
                    if approved:
                        changed[table]['approved_metadata_change'] = 'rpe_chart_source LF/CRLF hash only; every RPE table row identical'
                    if not approved and (missing or (added and table != 'app_settings')):
                        preserved = False
            changes[source] = {'changed_existing_tables': changed,
                               'new_tables': {t:s['count'] for t,s in new.items() if t not in old},
                               'counts': {t:s['count'] for t,s in new.items()},
                               'trial_hashes': {t:s['hash'] for t,s in new.items() if t.startswith('fatigue_trial')}}
        assert {name:digest(sources/name) for name in EXPECTED} == hashes
        report = {'input_hashes_match': True, 'original_copies_unchanged': True,
                  'baseline_revision': '1ce09768eda5252fc8bcc6c87768b8793d1b7470',
                  'network': 'Docker --network none plus Python connect guard',
                  'hevy_writes_enabled': False, 'startup_runs': 2,
                  'monitoring_outputs_equal': runs['baseline'] == runs['candidate'],
                  'cutoffs': list(runs['candidate']), 'existing_rows_preserved': preserved,
                  'databases': changes}
        (output/'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        if not preserved or not report['monitoring_outputs_equal']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
