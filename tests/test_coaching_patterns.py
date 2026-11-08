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
        week = result['weeks'][-1]
        self.assertEqual(3.5, week['patterns']['knee']['total'])
        self.assertEqual(6.5, week['patterns']['hip']['total'])
        self.assertEqual(0, week['patterns']['push']['total'])
        self.assertAlmostEqual(10, sum(p['total'] for p in week['patterns'].values()), places=1)
        self.assertAlmostEqual(5, sum(p['central'] for p in week['patterns'].values()), places=1)
        self.assertEqual(0, week['unmapped']['total'])

    def test_weeks_start_monday_use_local_dates_and_the_current_week_is_partial(self):
        scored = {'Bench': [(str(MONDAY - timedelta(days=1)), score(4.)), (str(MONDAY), score(6.)), (str(DAY), score(1.))]}
        result = self.rollup(scored, {'Bench': mapping(push=1.)})
        self.assertEqual(coaching_stress.WEEKS_SHOWN, len(result['weeks']))
        previous, current = result['weeks'][-2], result['weeks'][-1]
        self.assertEqual(str(MONDAY), current['week_start'])
        self.assertTrue(current['partial'])
        self.assertFalse(previous['partial'])
        self.assertEqual(4, previous['patterns']['push']['total'])
        self.assertEqual(7, current['patterns']['push']['total'])
        self.assertEqual(2, current['scored_movement_sessions'])
        self.assertEqual(str(MONDAY - timedelta(weeks=coaching_stress.WEEKS_SHOWN - 1)), result['weeks'][0]['week_start'])

    def test_missing_invalid_and_conditioning_mappings(self):
        scored = {name: [(str(DAY), score(2.))] for name in ('Mystery', 'Half', 'Metcon', 'Row')}
        result = self.rollup(scored, {'Half': mapping(knee=.5), 'Metcon': mapping(knee=1., conditioning=True),
                                      'Row': mapping(pull=1.)})
        week = result['weeks'][-1]
        self.assertEqual(4, week['unmapped']['total'])            # Mystery, plus Half whose weights sum to .5
        self.assertEqual(2, week['patterns']['pull']['total'])
        self.assertEqual(0, week['patterns']['knee']['total'])     # conditioning excluded; invalid weights not used
        self.assertEqual(['Half', 'Mystery'], result['unmapped_exercises'])
        self.assertEqual(3, week['scored_movement_sessions'])

    def test_typical_week_uses_completed_trained_weeks_only(self):
        rows = [(str(MONDAY - timedelta(weeks=weeks_ago)), score(total))
                for weeks_ago, total in ((1, 10.), (2, 20.), (3, 30.), (5, 50.))]   # week 4 is empty
        rows.append((str(DAY), score(99.)))                                         # the partial week is not typical
        result = self.rollup({'Bench': rows}, {'Bench': mapping(push=1.)})
        typical = result['typical_week']['push']
        self.assertEqual((25., 4, False), (typical['median'], typical['trained_weeks'], typical['provisional']))
        self.assertEqual(0, result['weeks'][-5]['patterns']['push']['total'])
        self.assertFalse(result['weeks'][-5]['trained'])
        few = self.rollup({'Bench': rows[:2]}, {'Bench': mapping(push=1.)})['typical_week']['push']
        self.assertTrue(few['provisional'])

    def test_rolling_windows_use_local_calendar_days(self):
        scored = {'Bench': [(str(DAY - timedelta(days=d)), score(1.)) for d in (0, 6, 7, 27, 28)]}
        result = self.rollup(scored, {'Bench': mapping(push=1.)})
        self.assertEqual(2, result['rolling_7_day']['patterns']['push']['total'])
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
        current = block['weeks'][-1]['patterns']
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
        again = coaching.build_report(self.db, today=DAY)['pattern_stress_index']['weeks'][-1]['patterns']
        self.assertAlmostEqual(session_total, again['knee']['total'], places=1)
        self.assertEqual(0, again['hip']['total'])

    def test_unmapped_exercises_stay_visible_in_the_report(self):
        self.imported('a', 3)
        block = coaching.build_report(self.db, today=DAY)['pattern_stress_index']
        self.assertEqual(['Squat'], block['unmapped_exercises'])
        self.assertGreater(block['weeks'][-1]['unmapped']['total'], 0)
        self.assertIsNone(block['reviewed_share'])

    def test_report_without_scorable_sessions_has_an_explicit_empty_block(self):
        self.assertEqual('no_scorable_sessions', coaching.build_report(self.db, today=DAY)['pattern_stress_index']['status'])

    def test_brief_separates_pattern_stress_index_from_the_host_card(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('pattern_stress_index attributes', 'It is not the host Pattern Stress card',
                       'These are totals, never limits or targets'):
            self.assertIn(phrase, brief)
