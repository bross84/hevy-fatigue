"""Session RPE feel check (#199) with isolated SQLite; no app startup, Hevy or real databases."""
from contextlib import closing
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import database
from database import AppSetting, Base, ExerciseMapping, WorkoutLog, WorkoutSession
import importer
from main import calculate_stress_scores
import srpe_modifier as sm

START = date(2026, 11, 1)


class PureRuleTests(unittest.TestCase):
    def test_gap_is_session_rpe_minus_the_mean_rated_set(self):
        self.assertEqual(sm.gap(9, [8, 7, None]), 1.5)
        self.assertIsNone(sm.gap(None, [8]))
        self.assertIsNone(sm.gap(8, [None, None]))

    def test_needs_five_earlier_rated_sessions(self):
        self.assertIsNone(sm.adjustment(1.0, [0.5] * 4))
        self.assertIsNotNone(sm.adjustment(1.0, [0.5] * 5))

    def test_five_percent_a_point_capped_at_fifteen(self):
        self.assertAlmostEqual(sm.adjustment(1.5, [0.5] * 6)['pct'], 0.05)
        self.assertAlmostEqual(sm.adjustment(-0.5, [0.5] * 6)['pct'], -0.05)
        self.assertEqual(sm.adjustment(6.0, [0.5] * 6)['pct'], 0.15)
        self.assertEqual(sm.adjustment(-6.0, [0.5] * 6)['pct'], -0.15)

    def test_usual_uses_only_the_last_ten(self):
        history = [5.0] * 20 + [0.0] * 10
        self.assertEqual(sm.adjustment(0.0, history)['usual_gap'], 0.0)

    def test_small_differences_have_no_note(self):
        self.assertIsNone(sm.note(0.01, 8, 7.9, 0.2))
        self.assertIn('Felt harder than usual', sm.note(0.05, 9, 8, 1.0))
        self.assertIn('Felt easier than usual', sm.note(-0.05, 7, 8, -1.0))


class StressModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(ExerciseMapping(exercise_title='Squat', pct_quad_dom=1.0, pct_posterior=0.0,
                                    pct_upper_push=0.0, pct_upper_pull=0.0))
        self.db.add(AppSetting(key=sm.START_SETTING, value=START.isoformat()))
        self.db.commit()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def add(self, key, day, srpe, set_rpe=8.0, modality='strength'):
        self.db.add(WorkoutSession(hevy_workout_id=key, workout_date=day, modality=modality,
                                   verification_status='verified', srpe=srpe, duration_minutes=50,
                                   start_time=datetime(day.year, day.month, day.day, 17)))
        for n in range(3):
            self.db.add(WorkoutLog(date=day, workout_id=key, exercise_id='sq', exercise_title='Squat',
                                   set_number=n, weight_lbs=300.0, reps=5, rpe=set_rpe, is_conditioning=False))
        self.db.commit()

    def history(self, gap=0.5, count=6, last=date(2026, 11, 20)):
        for i in range(count):
            self.add(f'h{i}', last - timedelta(days=2 * (count - i)), 8.0 + gap)

    def scores(self, day):
        return calculate_stress_scores(day, self.db)

    def baseline(self, day, key='today', set_rpe=8.0):
        """The same session without a session RPE: today's model."""
        self.db.query(WorkoutSession).filter_by(hevy_workout_id=key).update({'srpe': None})
        self.db.commit()
        return self.scores(day)

    def test_harder_than_usual_raises_only_whole_body_stress(self):
        self.history(gap=0.5)
        day = date(2026, 11, 22)
        self.add('today', day, 9.5)          # gap 1.5 vs usual 0.5: one point harder, +5%
        nudged = self.scores(day)
        plain = self.baseline(day)
        self.assertAlmostEqual(nudged['central'], round(plain['central'] * 1.05, 3), places=2)
        self.assertEqual((nudged['peripheral'], nudged['knee'], nudged['hip']),
                         (plain['peripheral'], plain['knee'], plain['hip']))

    def test_easier_than_usual_lowers_it_and_the_cap_holds(self):
        self.history(gap=0.5)
        day = date(2026, 11, 22)
        self.add('today', day, 4.0)          # gap -4 vs 0.5: capped at -15%
        nudged = self.scores(day)
        plain = self.baseline(day)
        self.assertAlmostEqual(nudged['central'], round(plain['central'] * 0.85, 3), places=2)

    def test_no_change_before_five_rated_sessions(self):
        self.history(count=4)
        day = date(2026, 11, 22)
        self.add('today', day, 10.0)
        self.assertEqual(self.scores(day), self.baseline(day))

    def test_no_change_before_the_start_date(self):
        self.history(last=date(2026, 10, 28))
        day = date(2026, 10, 30)
        self.add('today', day, 10.0)
        self.assertEqual(self.scores(day), self.baseline(day))

    def test_conditioning_sessions_keep_their_srpe_load_without_a_nudge(self):
        self.history()
        day = date(2026, 11, 22)
        self.add('today', day, 10.0, modality='conditioning')
        scores = self.scores(day)
        self.assertIsNone(sm.session_adjustment(self.db, database,
                                                self.db.query(WorkoutSession).filter_by(hevy_workout_id='today').one()))
        self.assertGreater(scores['central'], 0)

    def test_weekly_summary_flags_consistently_easier_sessions(self):
        self.history(gap=1.0)
        for i, day in enumerate([date(2026, 11, 21), date(2026, 11, 23), date(2026, 11, 25)]):
            self.add(f'easy{i}', day, 8.0)   # gap 0 vs usual 1: a point easier each time
        summary = sm.recent_summary(self.db, database, date(2026, 11, 26))
        self.assertTrue(summary['consistently_easier'])
        self.assertEqual(summary['easier_than_usual'], 3)


class ImportFillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / 'rack.db'
        env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(path))
        env.start()
        self.addCleanup(env.stop)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute('CREATE TABLE session_rpe (hevy_workout_id TEXT PRIMARY KEY, workout_start TEXT, rpe REAL, saved_at TEXT)')
            conn.execute("INSERT INTO session_rpe VALUES ('w1','2026-11-22T17:00:00Z',8.5,'now')")
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def test_log_value_fills_an_empty_session_only(self):
        self.db.add(WorkoutSession(hevy_workout_id='w1', workout_date=date(2026, 11, 22)))
        self.db.add(WorkoutSession(hevy_workout_id='w2', workout_date=date(2026, 11, 22), srpe=7.0))
        self.db.commit()
        importer._fill_srpe_from_log(self.db, 'w1')
        importer._fill_srpe_from_log(self.db, 'w2')
        self.assertEqual(self.db.query(WorkoutSession).filter_by(hevy_workout_id='w1').one().srpe, 8.5)
        self.assertEqual(self.db.query(WorkoutSession).filter_by(hevy_workout_id='w2').one().srpe, 7.0)

    def test_dashboard_value_wins_over_the_log(self):
        self.db.add(WorkoutSession(hevy_workout_id='w1', workout_date=date(2026, 11, 22), srpe=6.0))
        self.db.commit()
        importer._fill_srpe_from_log(self.db, 'w1')
        self.assertEqual(self.db.query(WorkoutSession).filter_by(hevy_workout_id='w1').one().srpe, 6.0)

    def test_missing_logger_database_means_no_value(self):
        with patch.dict(os.environ, RACKBOOK_DB_PATH=str(Path(self.temp.name) / 'absent.db')):
            self.assertIsNone(importer.logged_session_rpe('w1'))


if __name__ == '__main__':
    unittest.main()
