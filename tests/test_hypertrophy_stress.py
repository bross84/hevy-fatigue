"""Regression tests using isolated SQLite databases; no app startup or API calls."""
import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base, ExerciseMapping, WorkoutLog, WorkoutSession
from main import calculate_stress_scores
from rpe_table import get_set_central_stress, get_set_peripheral_stress


class HypertrophyStressTests(unittest.TestCase):
    day = date(2026, 5, 11)

    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(ExerciseMapping(
            exercise_title='Squat', pct_quad_dom=1.0, pct_posterior=0.0,
            pct_upper_push=0.0, pct_upper_pull=0.0,
        ))
        self.db.commit()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def add_session(self, workout_id='hyp', rpes=(None, None), **overrides):
        values = dict(hevy_workout_id=workout_id, workout_date=self.day,
                      modality='hypertrophy', verification_status='verified',
                      srpe=8.0, duration_minutes=24)
        values.update(overrides)
        self.db.add(WorkoutSession(**values))
        for number, rpe in enumerate(rpes):
            self.db.add(WorkoutLog(
                date=values['workout_date'], workout_id=workout_id,
                exercise_id='squat', exercise_title='Squat', set_number=number,
                weight_lbs=100.0, reps=10, rpe=rpe, is_conditioning=False,
            ))
        self.db.commit()

    def assert_stress(self, central, peripheral, knee=None, **kwargs):
        result = calculate_stress_scores(self.day, self.db, **kwargs)
        self.assertEqual(result, dict(
            central=round(central, 3), peripheral=round(peripheral, 3),
            knee=round(central + peripheral if knee is None else knee, 3),
            hip=0.0, push=0.0, pull=0.0,
        ))

    def per_set(self, rpes):
        return (
            sum(get_set_central_stress(100, 10, rpe, None, 'Squat', self.db) for rpe in rpes),
            sum(get_set_peripheral_stress(100, 10, rpe, None, 'Squat', self.db) for rpe in rpes),
        )

    def test_all_missing_rpe_uses_only_session_fallback(self):
        self.add_session()
        raw = 8 * 24 / 29
        self.assert_stress(raw, raw, knee=raw)

    def test_exactly_half_missing_replaces_even_rpe_logged_sets(self):
        self.add_session(rpes=(None, 8.0))
        raw = 8 * 24 / 29
        self.assert_stress(raw, raw, knee=raw)

    def test_zero_rpe_counts_as_missing(self):
        self.add_session(rpes=(0.0, 8.0))
        raw = 8 * 24 / 29
        self.assert_stress(raw, raw, knee=raw)

    def test_below_threshold_retains_per_set_stress(self):
        rpes = (None, 8.0, 8.0)
        self.add_session(rpes=rpes)
        self.assert_stress(*self.per_set(rpes))

    def test_ineligible_sessions_retain_per_set_stress(self):
        for override in (dict(verification_status='pending'), dict(srpe=None),
                         dict(duration_minutes=None), dict(modality='strength')):
            with self.subTest(override=override):
                self.db.query(WorkoutLog).delete()
                self.db.query(WorkoutSession).delete()
                self.db.commit()
                self.add_session(**override)
                self.assert_stress(*self.per_set((None, None)))

    def test_same_day_other_sessions_keep_their_stress(self):
        self.add_session()
        self.add_session('strength', (8.0,), modality='strength')
        self.add_session('hyp-rated', (8.0, 8.0))
        self.add_session('cardio', (), modality='cardio')
        c, p = self.per_set((8.0, 8.0, 8.0))
        raw = 8 * 24 / 29
        self.assert_stress(c + raw + raw * .3, p + raw + raw * .7,
                           knee=c + p + raw)

    def test_custom_hypertrophy_scale(self):
        self.add_session()
        self.assert_stress(8.0, 8.0, knee=8.0, hyp_scale=24.0,
                           conditioning_scale=100.0)

    def test_unmapped_fallback_keeps_equal_pattern_distribution(self):
        self.db.query(ExerciseMapping).delete()
        self.db.commit()
        self.add_session()
        raw = 8 * 24 / 29
        self.assertEqual(calculate_stress_scores(self.day, self.db), dict(
            central=round(raw * .25, 3), peripheral=round(raw, 3),
            knee=round(raw * .25, 3), hip=round(raw * .25, 3),
            push=round(raw * .25, 3), pull=round(raw * .25, 3),
        ))

    def test_other_dates_and_empty_sessions_do_not_trigger_fallback(self):
        self.add_session('yesterday', workout_date=self.day - timedelta(days=1))
        self.add_session('empty', ())
        self.assert_stress(0.0, 0.0)


if __name__ == '__main__':
    unittest.main()
