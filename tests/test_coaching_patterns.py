"""Weekly pattern attribution of stress for coaching reports: pure rules plus the report wiring."""
from copy import deepcopy
from datetime import date, datetime, timedelta
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
from database import Base, ExerciseMapping, WorkoutLog, WorkoutSession
from rackbook import database as logger

DAY = date(2026, 11, 5)
MONDAY = DAY - timedelta(days=DAY.weekday())


def score(total, sets_=1):
    return dict(total=total, central=total * .5, peripheral=total * 1.5, sets=sets_, estimated_sets=0, skipped_sets=0)


def mapping(knee=0., hip=0., push=0., pull=0., reviewed=True, conditioning=False):
    return dict(weights=dict(knee=knee, hip=hip, push=push, pull=pull), reviewed=reviewed, conditioning=conditioning)


class PatternRollupTests(TestCase):
    def rollup(self, scored, mappings, today=DAY):
        exercises = {name: dict(exercise_id=name, title=name) for name in scored}
        return coaching_stress.pattern_rollup(scored, exercises, mappings, today)

    def test_movement_stress_is_split_by_mapping_percentages_and_conserved(self):
        result = self.rollup({'Box Squat': [(str(DAY), score(10.))]}, {'Box Squat': mapping(knee=.35, hip=.65)})
        week = result['windows'][-1]
        self.assertEqual(3.5, week['patterns']['knee']['total'])
        self.assertEqual(6.5, week['patterns']['hip']['total'])
        self.assertEqual(0, week['patterns']['push']['total'])
        self.assertAlmostEqual(10, sum(p['total'] for p in week['patterns'].values()), places=1)
        self.assertAlmostEqual(5, sum(p['central'] for p in week['patterns'].values()), places=1)
        self.assertEqual(0, week['unmapped']['total'])

    def test_windows_are_rolling_7_days_ending_today_whatever_the_weekday(self):
        for today in (MONDAY, MONDAY + timedelta(days=3), MONDAY + timedelta(days=6)):
            with self.subTest(weekday=today.weekday()):
                # days ago: 0 and 6 share the latest window; 7 and 13 the one before; 62 the oldest; 63 is outside.
                scored = {'Bench': [(str(today - timedelta(days=d)), score(float(v)))
                                    for d, v in ((0, 1), (6, 2), (7, 4), (13, 8), (62, 16), (63, 32))]}
                result = self.rollup(scored, {'Bench': mapping(push=1.)}, today=today)
                self.assertEqual(coaching_stress.WINDOWS_SHOWN, len(result['windows']))
                self.assertEqual(7, result['window_days'])
                latest, previous, oldest = result['windows'][-1], result['windows'][-2], result['windows'][0]
                self.assertEqual((str(today - timedelta(days=6)), str(today)), (latest['window_start'], latest['window_end']))
                self.assertEqual((str(today - timedelta(days=13)), str(today - timedelta(days=7))),
                                 (previous['window_start'], previous['window_end']))
                self.assertEqual(str(today - timedelta(days=62)), oldest['window_start'])
                self.assertEqual(3, latest['patterns']['push']['total'])
                self.assertEqual(12, previous['patterns']['push']['total'])
                self.assertEqual(16, oldest['patterns']['push']['total'])
                self.assertEqual(2, latest['scored_movement_sessions'])
                self.assertNotIn('partial', latest)
                for left, right in zip(result['windows'], result['windows'][1:]):
                    self.assertEqual(str(date.fromisoformat(left['window_end']) + timedelta(days=1)), right['window_start'])

    def test_thursday_and_the_previous_friday_share_one_window(self):
        # A Monday calendar week would split these two sessions; the rolling window does not.
        scored = {'Bench': [(str(DAY), score(5.)), (str(DAY - timedelta(days=6)), score(7.))]}
        self.assertLess(DAY - timedelta(days=6), MONDAY)
        result = self.rollup(scored, {'Bench': mapping(push=1.)})
        self.assertEqual(12, result['windows'][-1]['patterns']['push']['total'])
        self.assertEqual(0, result['windows'][-2]['patterns']['push']['total'])

    def test_missing_invalid_and_conditioning_mappings(self):
        scored = {name: [(str(DAY), score(2.))] for name in ('Mystery', 'Half', 'Metcon', 'Row')}
        result = self.rollup(scored, {'Half': mapping(knee=.5), 'Metcon': mapping(knee=1., conditioning=True),
                                      'Row': mapping(pull=1.)})
        week = result['windows'][-1]
        self.assertEqual(4, week['unmapped']['total'])            # Mystery, plus Half whose weights sum to .5
        self.assertEqual(2, week['patterns']['pull']['total'])
        self.assertEqual(0, week['patterns']['knee']['total'])     # conditioning excluded; invalid weights not used
        self.assertEqual(['Half', 'Mystery'], result['unmapped_exercises'])
        self.assertEqual(3, week['scored_movement_sessions'])

    def test_typical_window_uses_earlier_trained_windows_only(self):
        # Window k holds days ago 7k..7k+6; window 4 is empty.
        rows = [(str(DAY - timedelta(days=days_ago)), score(total))
                for days_ago, total in ((10, 10.), (17, 20.), (24, 30.), (38, 50.))]
        rows.append((str(DAY), score(99.)))                                         # the latest window is not typical
        result = self.rollup({'Bench': rows}, {'Bench': mapping(push=1.)})
        typical = result['typical_window']['push']
        self.assertEqual((25., 4, False), (typical['median'], typical['trained_windows'], typical['provisional']))
        self.assertEqual(0, result['windows'][-5]['patterns']['push']['total'])
        self.assertFalse(result['windows'][-5]['trained'])
        few = self.rollup({'Bench': rows[:2]}, {'Bench': mapping(push=1.)})['typical_window']['push']
        self.assertTrue(few['provisional'])

    def test_rolling_28_day_total_uses_local_calendar_days(self):
        scored = {'Bench': [(str(DAY - timedelta(days=d)), score(1.)) for d in (0, 6, 7, 27, 28)]}
        result = self.rollup(scored, {'Bench': mapping(push=1.)})
        self.assertNotIn('rolling_7_day', result)             # the latest window is the last 7 days
        self.assertEqual(2, result['windows'][-1]['patterns']['push']['total'])
        self.assertEqual(4, result['rolling_28_day']['patterns']['push']['total'])

    def test_reviewed_share_and_unscorable_history(self):
        scored = {'A': [(str(DAY), score(3.))], 'B': [(str(DAY), score(1.))]}
        result = self.rollup(scored, {'A': mapping(knee=1., reviewed=True), 'B': mapping(hip=1., reviewed=False)})
        self.assertEqual(.75, result['reviewed_share'])
        for empty in ({}, {'A': [(str(DAY), score(0., sets_=0))]}, {'A': [('2025-01-01', score(5.))]},
                      {'A': [('bad', score(1.))]}, {'A': [(str(DAY + timedelta(days=1)), score(1.))]}):
            self.assertEqual('no_scorable_sessions', self.rollup(empty, {'A': mapping(knee=1.)})['status'])

    def test_inputs_are_not_mutated_and_output_is_json_safe(self):
        scored = {'A': [(str(DAY), score(3.))]}
        mappings = {'A': mapping(knee=.5, hip=.5)}
        before = deepcopy((scored, mappings))
        json.dumps(self.rollup(scored, mappings), allow_nan=False)
        self.assertEqual(before, (scored, mappings))

    def test_mapping_table_reads_orm_style_rows(self):
        row = ExerciseMapping(exercise_title='Squat', pct_quad_dom=.7, pct_posterior=.3, is_reviewed=True,
                              is_conditioning=False, pct_upper_push=None, pct_upper_pull=0.)
        self.assertEqual(dict(Squat=dict(weights=dict(knee=.7, hip=.3, push=0., pull=0.), reviewed=True, conditioning=False)),
                         coaching_stress.mapping_table([row]))


class PatternReportTests(TestCase):
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

    def imported(self, identity, days_ago, hour=17):
        day = DAY - timedelta(days=days_ago)
        self.db.add(WorkoutSession(hevy_workout_id=identity, workout_date=day, workout_title='Strength',
                                   start_time=datetime(day.year, day.month, day.day, hour)))
        self.db.add(WorkoutLog(workout_id=identity, date=day, exercise_id='sq', exercise_title='Squat', set_number=1,
                               weight_lbs=100 * 2.20462262185, reps=5, rpe=8))
        self.db.commit()

    def test_report_attributes_stress_by_current_mapping_and_edits_reattribute_history(self):
        self.imported('a', 10)
        self.imported('b', 3)
        self.db.add(ExerciseMapping(exercise_title='Squat', pct_quad_dom=.4, pct_posterior=.6, is_reviewed=True))
        self.db.commit()
        before = self.path.read_bytes()
        report = coaching.build_report(self.db, today=DAY)
        block = report['pattern_stress_index']
        session_total = report['exercises'][0]['stress']['latest_session']['total']
        current = block['windows'][-1]['patterns']
        self.assertAlmostEqual(session_total * .4, current['knee']['total'], places=1)
        self.assertAlmostEqual(session_total * .6, current['hip']['total'], places=1)
        self.assertEqual(1., block['reviewed_share'])
        self.assertEqual('rackbook-stress-v2', block['model_version'])
        self.assertEqual(coaching_stress.PATTERN_DESCRIPTION, block['description'])
        self.assertIn(coaching_stress.LIMITATIONS[-1], report['limitations'])
        self.assertEqual(before, self.path.read_bytes())
        row = self.db.query(ExerciseMapping).one()
        row.pct_quad_dom, row.pct_posterior = 1., 0.
        self.db.commit()
        again = coaching.build_report(self.db, today=DAY)['pattern_stress_index']['windows'][-1]['patterns']
        self.assertAlmostEqual(session_total, again['knee']['total'], places=1)
        self.assertEqual(0, again['hip']['total'])

    def test_unmapped_exercises_stay_visible_in_the_report(self):
        self.imported('a', 3)
        block = coaching.build_report(self.db, today=DAY)['pattern_stress_index']
        self.assertEqual(['Squat'], block['unmapped_exercises'])
        self.assertGreater(block['windows'][-1]['unmapped']['total'], 0)
        self.assertIsNone(block['reviewed_share'])

    def test_report_workload_and_pattern_windows_are_rolling_not_calendar_weeks(self):
        self.imported('fri', 6)      # the Friday before DAY (a Thursday): another calendar week
        self.imported('thu', 0)
        self.imported('old', 184)    # the first day of the six-month evidence window
        report = coaching.build_report(self.db, today=DAY)
        self.assertNotIn('weekly_workload', report)
        windows = report['workload_windows']
        latest, oldest = windows[-1], windows[0]
        self.assertEqual((str(DAY - timedelta(days=6)), str(DAY), 2, False),
                         (latest['window_start'], latest['window_end'], latest['sessions'], latest['partial']))
        self.assertEqual(str(DAY - timedelta(days=182)), oldest['window_end'])
        self.assertTrue(oldest['partial'])                    # starts before the evidence window
        self.assertEqual(2, report['pattern_stress_index']['windows'][-1]['scored_movement_sessions'])
        self.assertIn(coaching_stress.LIMITATIONS[-1], report['limitations'])
        self.assertTrue(any('rolling 7 local days' in text for text in report['limitations']))

    def test_report_without_scorable_sessions_has_an_explicit_empty_block(self):
        self.assertEqual('no_scorable_sessions', coaching.build_report(self.db, today=DAY)['pattern_stress_index']['status'])

    def test_brief_separates_pattern_stress_index_from_the_host_card(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('pattern_stress_index attributes', 'rolling 7-day windows', 'never calendar weeks',
                       'It is not the host Pattern Stress card',
                       'These are totals, never limits or targets'):
            self.assertIn(phrase, brief)
