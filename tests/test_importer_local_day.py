"""Imported Hevy workouts get the athlete's local training day. Mocked Hevy client, temporary SQLite."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase

SCRIPT = '''
from unittest.mock import Mock, patch
import main
from database import SessionLocal, WorkoutLog, WorkoutSession
main.startup()
raw = dict(id='late', title='Late squat', start_time='2026-11-16T04:35:00Z', end_time='2026-11-16T05:20:00Z',
           exercises=[dict(exercise_template_id='sq', title='Squat', sets=[dict(type='normal', weight_kg=100, reps=5, rpe=7)])])
client = Mock(); client.test_connection.return_value = True
client.get_workouts.return_value = {'workouts': [raw], 'page_count': 1}
client.get_workout_events.return_value = {'events': [], 'page_count': 1}
with patch('importer.HevyClient', return_value=client), SessionLocal() as db:
    main.trigger_sync_full(db=db)
    print(db.query(WorkoutSession).one().workout_date, db.query(WorkoutLog).one().date)
'''


class ImporterLocalDayTest(TestCase):
    def test_11pm_eastern_hevy_workout_is_dated_that_evening(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, 'DB_PATH': str(Path(folder) / 'host.db'), 'RACKBOOK_DB_PATH': str(Path(folder) / 'rack.db'),
                   'FERNET_KEY_PATH': str(Path(folder) / 'key'), 'HEVY_WRITES_ENABLED': '0',
                   'TZ': 'America/New_York', 'PYTHONIOENCODING': 'utf-8'}
            result = subprocess.run([sys.executable, '-c', SCRIPT], env=env, capture_output=True, text=True,
                                    encoding='utf-8', timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.split()[-2:], ['2026-11-15', '2026-11-15'])
