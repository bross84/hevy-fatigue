"""Stress-index evidence in coaching reports: read-only, temporary databases, no provider calls."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import coaching
import coaching_stress
from database import Base, WorkoutLog, WorkoutSession
from rackbook import database as logger
from rackbook import stress_index

DAY = date(2026, 11, 5)


def sets(kg, reps, rpe, role='working', n=1, conditioning=False):
    return [dict(exercise_id='sq', title='Squat', weight_kg=kg, reps=reps, actual_rpe=rpe, role=role,
                 conditioning=conditioning) for _ in range(n)]


def session(identity, day, start, entries):
    return dict(id=identity, date=str(day), title='Strength', start_time=start, sets=entries)


class PureStressEvidenceTests(TestCase):
    def test_start_times_are_normalised_to_utc_and_bad_values_rejected(self):
        self.assertEqual(datetime(2026, 11, 1, 12, tzinfo=timezone.utc), coaching_stress.utc_start('2026-11-01 12:00:00'))
        self.assertEqual(datetime(2026, 11, 1, 12, tzinfo=timezone.utc), coaching_stress.utc_start('2026-11-01T12:00:00Z'))
        self.assertEqual(datetime(2026, 11, 1, 16, tzinfo=timezone.utc), coaching_stress.utc_start('2026-11-01T12:00:00-04:00'))
        for bad in (None, '', 'nope', 12):
            self.assertIsNone(coaching_stress.utc_start(bad))

    def exercises(self):
        return {'sq': dict(exercise_id='sq', title='Squat')}

    def test_scores_match_the_stress_index_and_exclude_warmups_and_conditioning(self):
        working = sets(100, 5, 8, n=3)
        ordered = [session('a', DAY - timedelta(days=3), '2026-11-02 17:00:00',
                           working + sets(60, 5, 3, 'warmup') + sets(30, 20, 9, conditioning=True))]
        before = deepcopy(ordered)
        exercises = self.exercises()
        coaching_stress.attach(exercises, ordered, DAY)
        stress = exercises['sq']['stress']
        expected = stress_index.session_score([dict(weight_kg=100, reps=5, rpe=8)] * 3)
        self.assertEqual('rackbook-stress-v2', stress['model_version'])
        self.assertEqual(1, stress['scored_sessions'])
        self.assertAlmostEqual(expected['total'], stress['latest_session']['total'], places=2)
        self.assertEqual(3, stress['latest_session']['sets'])
        self.assertEqual('no_baseline', stress['latest_session']['status'])
        self.assertEqual(str(DAY - timedelta(days=3)), stress['latest_session']['date'])
        self.assertEqual(1, len(stress['recent_sessions']))
        self.assertEqual(before, ordered)

    def test_unscorable_history_is_labelled_not_scored_as_zero(self):
        ordered = [session('a', DAY, None, sets(100, 5, 8))]
        exercises = self.exercises()
        coaching_stress.attach(exercises, ordered, DAY)
        self.assertEqual(dict(status='no_scorable_sessions', unscored_sessions=1), exercises['sq']['stress'])

    def test_recent_sessions_are_bounded_and_baseline_uses_earlier_sessions_only(self):
        starts = [datetime(2026, 11, 4, 17) - timedelta(days=4 * (8 - i)) for i in range(9)]
        ordered = [session(str(i), start.date(), str(start), sets(100, 5, 8, n=3)) for i, start in enumerate(starts)]
        exercises = self.exercises()
        coaching_stress.attach(exercises, ordered, DAY)
        stress = exercises['sq']['stress']
        self.assertEqual(9, stress['scored_sessions'])
        self.assertEqual(coaching_stress.RECENT_SESSIONS, len(stress['recent_sessions']))
        self.assertEqual(3, stress['recent_sessions'][0]['baseline_sessions'])  # sessions 0-2 precede session 3
        self.assertEqual('usual', stress['latest_session']['status'])
        self.assertEqual(9, stress['typical_session']['baseline_sessions'])
        self.assertFalse(stress['typical_session']['provisional'])
        self.assertGreater(stress['rolling_28_day']['total'], stress['rolling_7_day']['total'])

    def test_late_evening_session_on_the_report_day_is_included(self):
        # Local date DAY, but 01:30 UTC the next day.
        ordered = [session('late', DAY, '2026-11-06 01:30:00', sets(100, 5, 8))]
        exercises = self.exercises()
        coaching_stress.attach(exercises, ordered, DAY)
        self.assertEqual(1, exercises['sq']['stress']['scored_sessions'])

    def test_exercise_without_scored_sets_gets_an_explicit_empty_block(self):
        exercises = {'row': dict(exercise_id='row', title='Row')}
        coaching_stress.attach(exercises, [session('a', DAY, '2026-11-05 12:00:00', sets(100, 5, 8))], DAY)
        self.assertEqual('no_scorable_sessions', exercises['row']['stress']['status'])
        self.assertEqual(0, exercises['row']['stress']['unscored_sessions'])


class ReportIntegrationTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'logging.db'
        self.env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(self.path))
        self.env.start()
        logger.init_db()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def imported(self, identity, day, start, kg=100, reps=5, rpe=8):
        self.db.add(WorkoutSession(hevy_workout_id=identity, workout_date=day, workout_title='Strength', start_time=start))
        self.db.add(WorkoutLog(workout_id=identity, date=day, exercise_id='sq', exercise_title='Squat', set_number=1,
                               weight_lbs=kg * 2.20462262185, reps=reps, rpe=rpe))
        self.db.commit()

    def exact(self, identity, day, *, kg, reps, rpe):
        at = f'{day}T17:00:00Z'
        raw = dict(exercise_template_id='sq', sets=[dict(review=dict(basis='e1rm', rpe_source='entered'))])
        with logger.get_db() as conn:
            conn.execute('INSERT INTO logged_sets (hevy_workout_id,workout_start,exercise_template_id,exercise_title,set_number,set_type,weight_kg,reps,rpe,is_ts,target_rpe) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (identity, at, 'sq', 'Squat', 1, 'normal', kg, reps, rpe, 1, 6))
            conn.execute('INSERT INTO session_reviews VALUES (?,?,?,?,?)',
                         (identity, at, json.dumps(dict(source='plan')), json.dumps([raw]), json.dumps(dict(title='Local session'))))

    def test_report_scores_merged_history_with_local_precedence_and_is_read_only(self):
        self.imported('a', DAY - timedelta(days=20), datetime(2026, 10, 16, 17))
        self.imported('b', DAY - timedelta(days=10), datetime(2026, 10, 26, 17))
        self.imported('c', DAY - timedelta(days=3), datetime(2026, 11, 2, 17), kg=90, rpe=None)
        self.exact('c', DAY - timedelta(days=3), kg=120, reps=3, rpe=9)
        before = self.path.read_bytes()
        report = coaching.build_report(self.db, today=DAY)
        self.assertEqual(before, self.path.read_bytes())
        stress = report['exercises'][0]['stress']
        self.assertEqual(3, stress['scored_sessions'])
        local = stress_index.session_score([dict(weight_kg=120, reps=3, rpe=9)],
                                           stress_index.session_e1rm([dict(weight_kg=100, reps=5, rpe=8)]))
        self.assertAlmostEqual(local['total'], stress['latest_session']['total'], places=2)
        self.assertEqual(0, stress['latest_session']['estimated_sets'])  # exact local RPE replaced the blank import
        self.assertEqual(2, stress['recent_sessions'][-1]['baseline_sessions'])
        self.assertEqual(coaching_stress.DESCRIPTION, report['stress_model'])
        for note in coaching_stress.LIMITATIONS:
            self.assertIn(note, report['limitations'])
        json.dumps(report, allow_nan=False)

    def test_sessions_without_start_time_are_unscored_and_labelled(self):
        self.imported('a', DAY, None)
        stress = coaching.build_report(self.db, today=DAY)['exercises'][0]['stress']
        self.assertEqual(dict(status='no_scorable_sessions', unscored_sessions=1), stress)

    def test_brief_tells_the_coach_how_to_use_stress(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('Rackbook stress index', 'Never add stress across movements',
                       'never call it a recovery limit, fatigue measurement or optimal zone',
                       'not a reason by itself to add or remove work'):
            self.assertIn(phrase, brief)

    def test_context_trimming_drops_session_detail_before_the_summary(self):
        for i in range(8):
            start = datetime(2026, 10, 1 + i * 3, 17)
            self.imported(str(i), start.date(), start)
        full = coaching.build_report(self.db, today=DAY)
        self.assertEqual(coaching_stress.RECENT_SESSIONS, len(full['exercises'][0]['stress']['recent_sessions']))
        trimmed = None
        for limit in range(len(coaching.encode(full)), 0, -150):
            try:
                candidate = coaching.build_report(self.db, today=DAY, context_limit=limit)
            except ValueError:
                break
            if any('Per-session stress detail omitted' in note for note in candidate['limitations']):
                trimmed = candidate
                break
        self.assertIsNotNone(trimmed)
        stress = trimmed['exercises'][0]['stress']
        self.assertNotIn('recent_sessions', stress)
        self.assertEqual('available', stress['status'])
        self.assertIn('latest_session', stress)
