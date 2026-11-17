"""Force Full Sync must keep what a person typed in for each workout session."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SETUP = '''
from datetime import datetime
from unittest.mock import Mock, patch
import main
from database import SessionLocal, WorkoutSession, AppSetting
main.startup()

def workout(identity, day):
    return {'id': identity, 'title': 'Session ' + identity,
            'start_time': day + 'T10:00:00Z', 'end_time': day + 'T11:00:00Z',
            'exercises': [{'exercise_template_id': 'sq', 'title': 'Squat (Barbell)',
                           'sets': [{'weight_kg': 80, 'reps': 5, 'rpe': 7, 'type': 'normal'}]}]}

workouts = [workout('w1', '2026-10-27'), workout('w2', '2026-10-28')]
client = Mock(); client.test_connection.return_value = True
client.get_workouts.return_value = {'workouts': workouts, 'page_count': 1}
client.get_workout_events.return_value = {'events': [], 'page_count': 1}

def typed_in(db):
    rows = {r.hevy_workout_id: r for r in db.query(WorkoutSession).all()}
    return rows

with patch('importer.HevyClient', return_value=client), SessionLocal() as db:
    main.trigger_sync(db=db)
    rows = typed_in(db)
    assert set(rows) == {'w1', 'w2'}, rows
    verified = rows['w1']
    verified.modality = 'conditioning'; verified.modality_confidence = 1.0
    verified.modality_note = 'typed note'; verified.duration_minutes = 42
    verified.srpe = 7.5; verified.verification_status = 'verified'
    verified.verified_at = datetime(2026, 10, 27, 12, 0, 0)
    rows['w2'].srpe = 6.0; rows['w2'].verification_status = 'pending'
    db.commit()

def assert_kept(db):
    rows = typed_in(db)
    w1, w2 = rows['w1'], rows['w2']
    assert (w1.modality, w1.modality_confidence, w1.modality_note, w1.duration_minutes, w1.srpe,
            w1.verification_status, w1.verified_at) == (
            'conditioning', 1.0, 'typed note', 42, 7.5, 'verified', datetime(2026, 10, 27, 12, 0, 0)), vars(w1)
    assert (w2.srpe, w2.verification_status) == (6.0, 'pending'), vars(w2)
    left = db.query(AppSetting).filter(AppSetting.key.in_(
        ['full_sync_preserved_sessions', 'sync_full_error_state'])).count()
    assert left == 0, left
'''

KEPT_AFTER_FULL_SYNC = SETUP + '''
with patch('importer.HevyClient', return_value=client), SessionLocal() as db:
    assert main.trigger_sync_full(db=db)['status'] == 'complete'
    assert_kept(db)
'''

KEPT_AFTER_FAILED_FULL_SYNC = SETUP + '''
from fastapi import HTTPException
broken = Mock(); broken.test_connection.return_value = True
calls = {'n': 0}
def fail_on_second_page(page):
    calls['n'] += 1
    if page == 1:
        return {'workouts': [workouts[0]], 'page_count': 2}
    raise RuntimeError('Hevy went away')
broken.get_workouts.side_effect = fail_on_second_page
with patch('importer.HevyClient', return_value=broken), SessionLocal() as db:
    try:
        main.trigger_sync_full(db=db)
        raise AssertionError('full sync should have failed')
    except HTTPException:
        pass
with SessionLocal() as db:
    rows = typed_in(db)
    assert rows['w1'].srpe is None and rows['w1'].verification_status != 'verified', vars(rows['w1'])
    assert db.query(AppSetting).filter(AppSetting.key == 'full_sync_preserved_sessions').count() == 1
# A second failed attempt must not replace the saved copy with the half-built rows.
with patch('importer.HevyClient', return_value=broken), SessionLocal() as db:
    try:
        main.trigger_sync_full(db=db)
    except HTTPException:
        pass
# Sync Now after the failure runs the full import (last_sync was cleared) and restores everything.
with patch('importer.HevyClient', return_value=client), SessionLocal() as db:
    assert main.trigger_sync(db=db)['status'] == 'complete'
    assert_kept(db)
'''


class FullSyncPreservesEntriesTests(unittest.TestCase):
    def run_script(self, script):
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, 'DB_PATH': str(Path(folder) / 'host.db'),
                   'RACKBOOK_DB_PATH': str(Path(folder) / 'rack.db'),
                   'FERNET_KEY_PATH': str(Path(folder) / 'key'),
                   'HEVY_WRITES_ENABLED': '0', 'PYTHONIOENCODING': 'utf-8'}
            result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True,
                                    text=True, encoding='utf-8', timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_full_sync_keeps_typed_in_session_details(self):
        self.run_script(KEPT_AFTER_FULL_SYNC)

    def test_failed_full_sync_keeps_a_copy_and_the_next_sync_restores_it(self):
        self.run_script(KEPT_AFTER_FAILED_FULL_SYNC)


if __name__ == '__main__':
    unittest.main()
