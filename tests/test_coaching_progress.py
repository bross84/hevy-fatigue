"""Progress/stall evidence in coaching reports: pure, read-only, temporary databases, no provider calls."""
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
import coaching_progress
from database import Base, WorkoutLog, WorkoutSession
from rackbook import database as logger

DAY = date(2026, 11, 5)


def work(kg, reps, rpe, source='entered', role='working', conditioning=False, exercise='sq'):
    return dict(exercise_id=exercise, title=exercise.upper(), weight_kg=kg, reps=reps, actual_rpe=rpe, role=role,
                rpe_source=source, conditioning=conditioning)


def session(days_ago, *entries, identity=None):
    day = DAY - timedelta(days=days_ago)
    return dict(id=identity or f'w{days_ago}-{len(entries)}', date=str(day), title='Strength', start_time=None,
                sets=list(entries))


def exposures(spec, **kwargs):
    """[(days_ago, kg)] -> sessions of one 5 @ RPE 8 set."""
    return [session(days_ago, work(kg, 5, 8, **kwargs), identity=f'w{days_ago}') for days_ago, kg in spec]


def progress(ordered, exercise='sq'):
    exercises = {exercise: dict(exercise_id=exercise, title=exercise.upper())}
    coaching_progress.attach(exercises, ordered, DAY)
    return exercises[exercise]['progress']


# Three exposures in the last 28 days, two in the 28 days before.
RECENT, EARLIER = (3, 10, 17), (33, 44)


class StatusTests(TestCase):
    def series(self, before, after):
        return exposures([(d, before) for d in EARLIER] + [(d, after) for d in RECENT])

    def test_a_clear_rise_is_progressing(self):
        block = progress(self.series(100, 108))
        self.assertEqual('progressing', block['status'])
        self.assertAlmostEqual(8.0, block['change_pct'], places=1)
        self.assertEqual(3, block['recent']['exposures'])
        self.assertEqual(2, block['previous']['exposures'])

    def test_noise_sized_differences_are_flat(self):
        for after in (98.5, 100, 102.4):
            self.assertEqual('flat', progress(self.series(100, after))['status'], after)

    def test_thresholds_are_inclusive_at_the_boundary(self):
        self.assertEqual('progressing', progress(self.series(100, 102.5))['status'])
        self.assertEqual('declining', progress(self.series(100, 95))['status'])
        self.assertEqual('flat', progress(self.series(100, 95.5))['status'])

    def test_a_clear_fall_is_declining(self):
        block = progress(self.series(100, 90))
        self.assertEqual('declining', block['status'])
        self.assertAlmostEqual(-10.0, block['change_pct'], places=1)

    def test_one_bad_day_does_not_flip_the_level(self):
        ordered = exposures([(d, 100) for d in EARLIER] + [(3, 100), (10, 80), (17, 100)])
        self.assertEqual('flat', progress(ordered)['status'])

    def test_one_outlier_high_day_does_not_read_as_progress(self):
        ordered = exposures([(d, 100) for d in EARLIER] + [(3, 100), (10, 130), (17, 100)])
        self.assertEqual('flat', progress(ordered)['status'])

    def test_too_few_recent_exposures_is_insufficient_not_flat(self):
        block = progress(exposures([(d, 100) for d in EARLIER] + [(3, 100), (10, 100)]))
        self.assertEqual(dict(status='insufficient_evidence', reason='too_few_recent_exposures', recent_exposures=2),
                         {k: block[k] for k in ('status', 'reason', 'recent_exposures')})
        self.assertNotIn('change_pct', block)

    def test_too_little_earlier_history_is_insufficient(self):
        block = progress(exposures([(33, 100)] + [(d, 100) for d in RECENT]))
        self.assertEqual('insufficient_evidence', block['status'])
        self.assertEqual('too_little_earlier_history', block['reason'])
        self.assertEqual(1, block['previous_exposures'])

    def test_a_movement_not_trained_recently_is_insufficient(self):
        block = progress(exposures([(40, 100), (50, 100)]))
        self.assertEqual('too_few_recent_exposures', block['reason'])
        self.assertEqual(0, block['recent_exposures'])

    def test_period_edges_are_exact(self):
        # 27 days ago is the oldest recent day; 28 days ago is the newest earlier day.
        ordered = exposures([(27, 100), (20, 100), (14, 100), (28, 100), (35, 100)])
        block = progress(ordered)
        self.assertEqual((3, 2), (block['recent']['exposures'], block['previous']['exposures']))
        # 55 days ago is the oldest earlier day; 56 days ago and future days are ignored.
        ordered = exposures([(55, 100), (56, 100), (3, 100), (10, 100), (17, 100), (-1, 150)])
        block = progress(ordered)
        self.assertEqual('too_little_earlier_history', block['reason'])
        self.assertEqual(1, block['previous_exposures'])
        self.assertEqual(4, block['eligible_exposures'])


class EligibilityTests(TestCase):
    def test_warmups_conditioning_and_unknown_loads_are_not_used(self):
        ordered = [session(3, work(200, 5, 9, role='warmup'), work(150, 20, 9, conditioning=True),
                           work(None, 5, 8), work(100, 5, 8))]
        block = progress(ordered)
        self.assertEqual(1, block['eligible_exposures'])
        self.assertEqual(0, block['unusable_exposures'])

    def test_blank_rpe_sessions_are_unusable_and_never_anchor(self):
        block = progress([session(3, work(150, 5, None)), session(10, work(100, 5, 8), work(150, 5, None))])
        self.assertEqual(1, block['eligible_exposures'])
        self.assertEqual(1, block['unusable_exposures'])

    def test_light_sessions_are_counted_but_excluded(self):
        block = progress([session(3, work(60, 5, 6.5)), session(10, work(100, 5, 7))])
        self.assertEqual(1, block['eligible_exposures'])
        self.assertEqual(1, block['low_effort_exposures'])

    def test_the_heaviest_recorded_set_anchors_the_exposure(self):
        ordered = [session(3, work(100, 5, 8), work(120, 3, 8.5), work(90, 8, 9))]
        self.assertEqual(120, coaching_progress.collect(ordered, DAY)['sq']['points'][0]['weight_kg'])

    def test_a_deload_week_below_the_effort_floor_does_not_read_as_a_decline(self):
        ordered = exposures([(d, 100) for d in EARLIER] + [(3, 100), (10, 100)])
        ordered.append(session(17, work(70, 5, 6), identity='deload'))
        block = progress(ordered)
        self.assertEqual('too_few_recent_exposures', block['reason'])
        self.assertEqual(1, block['low_effort_exposures'])

    def test_unrelated_movements_are_tracked_separately(self):
        ordered = exposures([(d, 100) for d in EARLIER + RECENT]) + [session(3, work(50, 5, 8, exercise='row'))]
        found = coaching_progress.collect(ordered, DAY)
        self.assertEqual(5, len(found['sq']['points']))
        self.assertEqual(1, len(found['row']['points']))


class ConfounderTests(TestCase):
    def test_rep_range_shift_is_flagged(self):
        ordered = [session(d, work(100, 5, 8), identity=f'a{d}') for d in EARLIER]
        ordered += [session(d, work(80, 10, 8), identity=f'b{d}') for d in RECENT]
        block = progress(ordered)
        self.assertTrue(block['rep_range_shift'])
        self.assertEqual(5, block['previous']['median_anchor_reps'])
        self.assertEqual(10, block['recent']['median_anchor_reps'])

    def test_a_steady_rep_range_is_not_flagged(self):
        block = progress(exposures([(d, 100) for d in EARLIER + RECENT]))
        self.assertFalse(block['rep_range_shift'])

    def test_imported_rpe_provenance_is_reported(self):
        ordered = exposures([(d, 100) for d in EARLIER], source='hevy_import')
        ordered += exposures([(3, 100), (10, 100)], source='entered') + exposures([(17, 100)], source='hevy_import')
        block = progress(ordered)
        self.assertEqual(0.67, block['recent']['entered_share'])
        self.assertEqual(0.0, block['previous']['entered_share'])

    def test_high_rep_exposures_are_counted_not_dropped(self):
        ordered = [session(d, work(40, 15, 8), identity=f'h{d}') for d in EARLIER + RECENT]
        block = progress(ordered)
        self.assertEqual(5, block['high_rep_exposures'])
        self.assertNotEqual('insufficient_evidence', block['status'])

    def test_best_and_exposures_since_best(self):
        ordered = exposures([(44, 100), (33, 100), (17, 110), (10, 100), (3, 100)])
        block = progress(ordered)
        self.assertEqual(str(DAY - timedelta(days=17)), block['best_date'])
        self.assertEqual(2, block['exposures_since_best'])
        self.assertEqual(5, len(block['recent_points']))
        self.assertEqual(str(DAY - timedelta(days=44)), block['recent_points'][0]['date'])

    def test_recent_points_are_bounded(self):
        ordered = exposures([(d, 100) for d in (3, 6, 9, 12, 15, 18, 21, 33, 44)])
        self.assertEqual(coaching_progress.RECENT_SHOWN, len(progress(ordered)['recent_points']))


class SummaryTests(TestCase):
    def build(self, specs):
        ordered, exercises = [], {}
        for name, before, after in specs:
            exercises[name] = dict(exercise_id=name, title=name.title())
            for d in EARLIER:
                ordered.append(session(d, work(before, 5, 8, exercise=name), identity=f'{name}{d}'))
            for d in RECENT:
                ordered.append(session(d, work(after, 5, 8, exercise=name), identity=f'{name}{d}'))
        before = deepcopy(ordered)
        summary = coaching_progress.attach(exercises, ordered, DAY)
        self.assertEqual(before, ordered)
        return summary, exercises

    def test_counts_and_attention_order(self):
        summary, _ = self.build([('bench', 100, 110), ('squat', 100, 100), ('row', 100, 85), ('curl', 100, 101)])
        self.assertEqual(dict(progressing=1, flat=2, declining=1, insufficient_evidence=0), summary['movements'])
        self.assertEqual(['row', 'curl', 'squat'], [f['exercise_id'] for f in summary['attention']])
        self.assertEqual('declining', summary['attention'][0]['status'])
        self.assertEqual(3, summary['attention_total'])
        self.assertEqual(coaching_progress.DESCRIPTION, summary['description'])

    def test_attention_is_capped_but_the_total_is_kept(self):
        summary, _ = self.build([(f'm{i:02d}', 100, 100) for i in range(coaching_progress.MAX_FLAGS + 3)])
        self.assertEqual(coaching_progress.MAX_FLAGS, len(summary['attention']))
        self.assertEqual(coaching_progress.MAX_FLAGS + 3, summary['attention_total'])

    def test_movements_without_evidence_are_never_flagged(self):
        exercises = {'x': dict(exercise_id='x', title='X')}
        summary = coaching_progress.attach(exercises, [], DAY)
        self.assertEqual('insufficient_evidence', exercises['x']['progress']['status'])
        self.assertEqual([], summary['attention'])
        self.assertEqual(0, summary['attention_total'])

    def test_assess_at_matches_attach_and_ignores_later_sessions(self):
        _, exercises = self.build([('bench', 100, 110)])
        ordered = [session(d, work(100 if d in EARLIER else 110, 5, 8, exercise='bench'), identity=f'b{d}')
                   for d in EARLIER + RECENT]
        blocks = coaching_progress.assess_at(ordered, DAY, ['bench', 'absent'])
        self.assertEqual(exercises['bench']['progress'], blocks['bench'])
        self.assertEqual('too_few_recent_exposures', blocks['absent']['reason'])
        # Sessions after the as-of date are invisible, so history can be replayed: only the
        # exposures 10, 17, 33 and 44 days ago existed ten days earlier.
        past = coaching_progress.assess_at(ordered, DAY - timedelta(days=10), ['bench'])['bench']
        self.assertEqual(4, past['eligible_exposures'])

    def test_output_is_json_serialisable(self):
        summary, exercises = self.build([('bench', 100, 110)])
        json.dumps([summary, exercises], allow_nan=False, default=str)


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

    def imported(self, identity, days_ago, kg):
        day = DAY - timedelta(days=days_ago)
        self.db.add(WorkoutSession(hevy_workout_id=identity, workout_date=day, workout_title='Strength',
                                   start_time=datetime(day.year, day.month, day.day, 17)))
        self.db.add(WorkoutLog(workout_id=identity, date=day, exercise_id='sq', exercise_title='Squat', set_number=1,
                               weight_lbs=kg * 2.20462262185, reps=5, rpe=8))

    def seed(self, before, after):
        for days_ago in EARLIER:
            self.imported(f'e{days_ago}', days_ago, before)
        for days_ago in RECENT:
            self.imported(f'r{days_ago}', days_ago, after)
        self.db.commit()

    def test_report_carries_progress_without_touching_the_logger_database(self):
        self.seed(100, 90)
        before = self.path.read_bytes()
        report = coaching.build_report(self.db, today=DAY)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual('declining', report['exercises'][0]['progress']['status'])
        summary = report['progress_summary']
        self.assertEqual(['sq'], [f['exercise_id'] for f in summary['attention']])
        self.assertEqual(1, summary['movements']['declining'])
        for note in coaching_progress.LIMITATIONS:
            self.assertIn(note, report['limitations'])
        json.dumps(report, allow_nan=False)

    def test_a_progressing_movement_is_not_put_in_attention(self):
        self.seed(100, 110)
        report = coaching.build_report(self.db, today=DAY)
        self.assertEqual('progressing', report['exercises'][0]['progress']['status'])
        self.assertEqual([], report['progress_summary']['attention'])

    def test_brief_frames_progress_as_context_not_a_recommendation(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('progress_summary.attention', 'not a daily interpretation',
                       'rep_range_shift', 'shows neither cause nor failure',
                       'never present it as proof that a block should end'):
            self.assertIn(phrase, brief)

    def test_context_trimming_drops_progress_points_before_the_summary(self):
        self.seed(100, 100)
        full = coaching.build_report(self.db, today=DAY)
        self.assertIn('recent_points', full['exercises'][0]['progress'])
        trimmed = None
        for limit in range(len(coaching.encode(full)), 0, -100):
            try:
                candidate = coaching.build_report(self.db, today=DAY, context_limit=limit)
            except ValueError:
                break
            if any('Per-exposure progress points omitted' in note for note in candidate['limitations']):
                trimmed = candidate
                break
        self.assertIsNotNone(trimmed)
        block = trimmed['exercises'][0]['progress']
        self.assertNotIn('recent_points', block)
        self.assertEqual('flat', block['status'])
        self.assertIn('change_pct', block)
