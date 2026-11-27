"""Session advice reads the host database built by the real host schema (#147).

rackbook/tests/test_session_advice.py builds the host tables by hand, so a host
schema change would still pass there while session advice silently turned off
(host_context swallows database errors). This test builds the host database with
database.init_db() and writes rows through the SQLAlchemy models, so the stored
names and formats are the ones production uses. Disposable SQLite only.
"""
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
from rackbook import main as training, session_advice as advice

NOW = datetime(2026, 11, 5, 15, tzinfo=timezone.utc)
TODAY = NOW.date()


class SessionAdviceHostSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        host = Path(self.tmp.name) / 'host.db'
        self.engine = create_engine('sqlite:///' + str(host), connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        with patch.object(database, 'engine', self.engine):
            database.init_db()
        env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(Path(self.tmp.name) / 'logging.db'),
                         HEVY_FATIGUE_DB_PATH=str(host))
        env.start()
        self.addCleanup(env.stop)
        training.initialize()
        self.seed()

    def seed(self):
        with sessionmaker(bind=self.engine)() as db:
            db.add(database.DailyReadiness(date=TODAY, tiredness=3, perceived_recovery=2, sore_quad_dom=1,
                                           sore_posterior=0, sore_upper_push=0, sore_upper_pull=0,
                                           joint_upper=1, joint_lower=0))
            db.add(database.DailyReadiness(date=TODAY - timedelta(days=10), tiredness=0, perceived_recovery=0))
            for i in range(3):
                start = datetime(2026, 11, 2 + i, 15)
                workout_id = f'hevy-{i}'
                db.add(database.WorkoutSession(hevy_workout_id=workout_id, workout_date=start.date(),
                                               workout_title='ST Squat', start_time=start))
                for n in range(3):
                    db.add(database.WorkoutLog(date=start.date(), workout_title='ST Squat', exercise_title='Squat',
                                               set_number=n + 1, workout_id=workout_id, exercise_id='sq',
                                               weight_lbs=225.0, reps=5, rpe=6.0))
            db.add(database.WorkoutLog(date=date(2026, 11, 3), exercise_title='Bench Press', set_number=1,
                                       workout_id='hevy-1', exercise_id='bench', weight_lbs=185.0, reps=5, rpe=7.0))
            db.commit()

    def test_host_context_reads_checkins_and_history_from_the_real_schema(self):
        host = advice.host_context(TODAY, 'sq', NOW - timedelta(minutes=10))

        self.assertEqual((host['status'], host['history_status']), ('available', 'available'))
        self.assertEqual(len(host['checkins']), 1)
        self.assertEqual(host['checkins'][0], dict(date=TODAY.isoformat(), tiredness=3, perceived_recovery=2,
                                                   sore_quad_dom=1, sore_posterior=0, sore_upper_push=0,
                                                   sore_upper_pull=0, joint_upper=1, joint_lower=0))
        self.assertEqual(len(host['history']), 9)
        self.assertEqual({row['exercise_template_id'] for row in host['history']}, {'sq'})
        first = host['history'][0]
        self.assertEqual((first['hevy_workout_id'], first['workout_date'], first['set_number'],
                          first['weight_lbs'], first['reps'], first['rpe']),
                         ('hevy-0', '2026-11-02', 1, 225.0, 5, 6.0))
        self.assertEqual(advice.stamp(first['workout_start']), datetime(2026, 11, 2, 15, tzinfo=timezone.utc))

    def test_advice_uses_host_checkins_and_imported_history(self):
        data = advice.AdviceRequest(session_id=uuid4(), exercise_id='movement', exercise_template_id='sq',
                                    title='Squat', workout_start=NOW - timedelta(minutes=10), local_date=TODAY,
                                    sets=[dict(reps=5, rpe=6) for _ in range(3)])

        row = advice.create(data, now=NOW)

        self.assertEqual(row['evidence']['checkins'][0]['tiredness'], 3)
        self.assertEqual(row['evidence']['history_workouts'], 3)


if __name__ == '__main__':
    unittest.main()
