"""Outcome review of saved AI week proposals: pure, read-only, temporary databases, no provider calls."""
from contextlib import closing
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import coaching
import coaching_outcomes
import coaching_progress
from database import Base, WorkoutLog, WorkoutSession
from rackbook import database as logger

DAY = date(2026, 11, 5)
SAVED = '2026-09-20T15:00:00+00:00'      # 46 days before DAY
BEFORE_FLAT = ['2026-08-01', '2026-08-08', '2026-08-29', '2026-09-05', '2026-09-12']
AFTER_UP = [('2026-09-26', 100), ('2026-10-03', 100), ('2026-10-16', 110), ('2026-10-23', 110), ('2026-10-30', 110)]


def day(text):
    return date.fromisoformat(text)


def work(kg, exercise='sq', reps=5, rpe=8):
    return dict(exercise_id=exercise, title=exercise.upper(), weight_kg=kg, reps=reps, actual_rpe=rpe,
                role='working', rpe_source='entered', conditioning=False)


def sessions(points, exercise='sq', reps=5):
    return [dict(id=f'{exercise}-{when}', date=when, title='S', start_time=None, sets=[work(kg, exercise, reps)])
            for when, kg in points]


def history():
    return sorted(sessions([(d, 100) for d in BEFORE_FLAT] + AFTER_UP), key=lambda s: s['date'])


def proposed(*, title='Hypertrophy week', moves=(('sq', 'Squat', (8, 8, 10)),)):
    exercises = [dict(exercise_template_id=i, title=t, notes='',
                      sets=[dict(reps=r, rpe=7, ts=False, type='normal') for r in reps]) for i, t, reps in moves]
    return json.dumps(dict(version='plan-proposal-v1', title=title, rationale='r',
                           sessions=[dict(name='Day', exercises=exercises)]))


def plan(*, revision=1, active=0, archived=0, ids=('s1', 's2')):
    movement = dict(exercise_template_id='sq', title='Squat', sets=[dict(reps=8, rpe=7)])
    document = dict(name='AI', weeks=[dict(name='Week 1', sessions=[dict(id=i, exercises=[movement]) for i in ids]
                                           + [dict(id='rest', exercises=[])])])
    return dict(id='p1', active=active, archived=archived, revision=revision, document=json.dumps(document))


def proposal(identity='a', saved=SAVED, plan_id='p1', **kwargs):
    return dict(id=identity, plan_id=plan_id, proposed=proposed(**kwargs), saved_at=saved)


def done(*pairs):
    return {'p1': [dict(session_id=s, workout_start=f'{when}T17:00:00Z') for s, when in pairs]}


def one(rows, plans, completions, ordered=None):
    return coaching_outcomes.review(rows, plans, completions, history() if ordered is None else ordered, DAY)[0]


class StageTests(TestCase):
    def stage(self, plans, completions):
        return one([proposal()], plans, completions)['stage']

    def test_each_stage(self):
        self.assertEqual('plan_removed', self.stage({}, {}))
        self.assertEqual('not_started', self.stage({'p1': plan()}, {}))
        self.assertEqual('active_not_started', self.stage({'p1': plan(active=1)}, {}))
        self.assertEqual('archived_unused', self.stage({'p1': plan(archived=1)}, {}))
        self.assertEqual('in_progress', self.stage({'p1': plan()}, done(('s1', '2026-10-01'))))
        self.assertEqual('completed', self.stage({'p1': plan()}, done(('s1', '2026-10-01'), ('s2', '2026-10-08'))))

    def test_skipped_days_finish_the_plan_without_counting_as_trained(self):
        rows = done(('s1', '2026-10-01'))['p1'] + [dict(session_id='s2', workout_start='2026-10-08T17:00:00Z', outcome='skipped')]
        item = one([proposal()], {'p1': plan()}, {'p1': rows})
        self.assertEqual(('finished_with_skips', 1, 1, '2026-10-01', 'available'),
                         (item['stage'], item['sessions_completed'], item['sessions_skipped'], item['first_completed'], item['comparison']))

    def test_a_plan_of_only_skips_was_never_executed(self):
        rows = [dict(session_id=s, workout_start='2026-10-01T17:00:00Z', outcome='skipped') for s in ('s1', 's2')]
        item = one([proposal()], {'p1': plan()}, {'p1': rows})
        self.assertEqual(('finished_with_skips', 'not_executed', 0, 2, None),
                         (item['stage'], item['comparison'], item['sessions_completed'], item['sessions_skipped'], item['first_completed']))

    def test_a_partly_skipped_plan_is_still_in_progress(self):
        rows = [dict(session_id='s1', workout_start='2026-10-01T17:00:00Z', outcome='skipped')]
        self.assertEqual('in_progress', one([proposal()], {'p1': plan()}, {'p1': rows})['stage'])

    def test_a_session_without_exercises_does_not_block_completion(self):
        item = one([proposal()], {'p1': plan()}, done(('s1', '2026-10-01'), ('s2', '2026-10-08')))
        self.assertEqual((2, 2), (item['sessions_planned'], item['sessions_completed']))

    def test_edits_are_flagged_by_revision(self):
        self.assertFalse(one([proposal()], {'p1': plan()}, {})['edited_since_save'])
        self.assertTrue(one([proposal()], {'p1': plan(revision=2)}, {})['edited_since_save'])
        self.assertFalse(one([proposal()], {}, {})['edited_since_save'])

    def test_a_removed_plan_has_no_planned_count(self):
        self.assertIsNone(one([proposal()], {}, {})['sessions_planned'])


class ComparisonTests(TestCase):
    def comparison(self, first):
        return one([proposal()], {'p1': plan()}, done(('s1', first)))['comparison']

    def test_not_executed_shows_no_progress_comparison(self):
        item = one([proposal()], {'p1': plan()}, {})
        self.assertEqual('not_executed', item['comparison'])
        self.assertEqual([dict(exercise_id='sq', title='Squat', proposed_reps=[8, 10])], item['movements'])
        self.assertNotIn('before_as_of', item)

    def test_twenty_eight_days_after_the_first_session_is_the_boundary(self):
        self.assertEqual('too_early', self.comparison(str(DAY - timedelta(days=27))))
        self.assertEqual('available', self.comparison(str(DAY - timedelta(days=28))))

    def test_too_early_reports_execution_but_not_progress(self):
        item = one([proposal()], {'p1': plan()}, done(('s1', str(DAY - timedelta(days=10)))))
        self.assertEqual(10, item['days_since_first_completion'])
        self.assertNotIn('before', item['movements'][0])

    def test_before_and_after_use_the_logs_as_of_each_date(self):
        item = one([proposal()], {'p1': plan()}, done(('s1', '2026-10-01'), ('s2', '2026-10-08')))
        self.assertEqual('available', item['comparison'])
        self.assertEqual(('2026-09-19', '2026-11-05'), (item['before_as_of'], item['after_as_of']))
        self.assertEqual((2026, 35), (day(item['first_completed']).year, item['days_since_first_completion']))
        move = item['movements'][0]
        self.assertEqual([8, 10], move['proposed_reps'])
        self.assertEqual('flat', move['before']['status'])
        self.assertEqual('progressing', move['after']['status'])
        self.assertAlmostEqual(10.0, move['after']['change_pct'], places=1)
        self.assertEqual(5, move['after']['median_anchor_reps'])

    def test_later_sessions_never_leak_into_the_before_view(self):
        moves = coaching_progress.assess_at(history(), day('2026-09-19'), ['sq'])['sq']
        self.assertEqual(('flat', 3, 2), (moves['status'], moves['recent']['exposures'], moves['previous']['exposures']))

    def test_missing_history_is_insufficient_not_invented(self):
        item = one([proposal()], {'p1': plan()}, done(('s1', '2026-10-01')), ordered=[])
        move = item['movements'][0]
        self.assertEqual('too_few_recent_exposures', move['before']['reason'])
        self.assertEqual('insufficient_evidence', move['after']['status'])

    def test_rep_range_change_is_visible(self):
        ordered = sorted(sessions([(d, 100) for d in BEFORE_FLAT + ['2026-09-26', '2026-10-03']], reps=5)
                         + sessions([('2026-10-16', 80), ('2026-10-23', 80), ('2026-10-30', 80)], reps=10), key=lambda s: s['date'])
        item = one([proposal()], {'p1': plan()}, done(('s1', '2026-10-01')), ordered=ordered)
        move = item['movements'][0]
        self.assertEqual(5, move['before']['median_anchor_reps'])
        self.assertEqual(10, move['after']['median_anchor_reps'])


class ShapeTests(TestCase):
    def test_newest_first_and_capped(self):
        rows = [proposal(identity=f'p{i}', saved=f'2026-10-0{i}T10:00:00+00:00') for i in range(1, 8)]
        result = coaching_outcomes.review(rows, {}, {}, [], DAY)
        self.assertEqual(coaching_outcomes.MAX_PROPOSALS, len(result))
        self.assertEqual(['p7', 'p6', 'p5', 'p4', 'p3'], [r['proposal_id'] for r in result])

    def test_movements_are_deduplicated_ordered_and_capped(self):
        moves = tuple((f'm{i}', f'Move {i}', (5,)) for i in range(coaching_outcomes.MAX_MOVEMENTS + 3))
        item = one([proposal(moves=moves + (('m0', 'Move 0', (3,)),))], {}, {})
        self.assertEqual(coaching_outcomes.MAX_MOVEMENTS, len(item['movements']))
        self.assertEqual('m0', item['movements'][0]['exercise_id'])
        self.assertEqual([3, 5], item['movements'][0]['proposed_reps'])

    def test_unreadable_proposal_text_does_not_raise(self):
        for bad in ('not json', '[]', None, '{"sessions": [{"exercises": [{"sets": []}]}]}'):
            row = dict(proposal(), proposed=bad)
            item = coaching_outcomes.review([row], {}, {}, [], DAY)[0]
            self.assertEqual([], item['movements'])

    def test_inputs_are_not_mutated_and_output_is_json(self):
        args = ([proposal()], {'p1': plan()}, done(('s1', '2026-10-01')), history())
        before = deepcopy(args)
        result = coaching_outcomes.review(*args, DAY)
        self.assertEqual(before, args)
        json.dumps(result, allow_nan=False)

    def test_no_proposals_gives_an_empty_list(self):
        self.assertEqual([], coaching_outcomes.review([], {}, {}, history(), DAY))


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
        for n, (when, kg) in enumerate([(d, 100) for d in BEFORE_FLAT] + AFTER_UP):
            moment = day(when)
            self.db.add(WorkoutSession(hevy_workout_id=f'w{n}', workout_date=moment, workout_title='Strength',
                                       start_time=datetime(moment.year, moment.month, moment.day, 17)))
            self.db.add(WorkoutLog(workout_id=f'w{n}', date=moment, exercise_id='sq', exercise_title='Squat',
                                   set_number=1, weight_lbs=kg * 2.20462262185, reps=5, rpe=8))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def save(self, identity='a', saved=SAVED, plan_id='p1'):
        with logger.get_db() as conn:
            if not conn.execute('SELECT 1 FROM mesocycles WHERE id=?', (plan_id,)).fetchone():
                conn.execute('INSERT INTO mesocycles (id, document, revision) VALUES (?,?,?)',
                             (plan_id, plan()['document'], 1))
            conn.execute('INSERT INTO plan_proposals (id,conversation_id,turn_id,plan_id,proposed,saved_at) VALUES (?,?,?,?,?,?)',
                         (identity, f'c-{identity}', f't-{identity}', plan_id, proposed(), saved))

    def complete(self, *pairs, plan_id='p1'):
        with logger.get_db() as conn:
            for session_id, when in pairs:
                conn.execute('INSERT INTO mesocycle_completions (mesocycle_id,session_id,hevy_workout_id,workout_start) VALUES (?,?,?,?)',
                             (plan_id, session_id, None, f'{when}T17:00:00Z'))

    def test_report_carries_outcomes_and_stays_read_only(self):
        self.save()
        self.complete(('s1', '2026-10-01'))
        before = self.path.read_bytes()
        report = coaching.build_report(self.db, today=DAY)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual('available', report['coverage']['local_source'])
        item = report['proposal_outcomes'][0]
        self.assertEqual(('in_progress', 'available', 1, 2), (item['stage'], item['comparison'], item['sessions_completed'], item['sessions_planned']))
        self.assertEqual(('flat', 'progressing'), (item['movements'][0]['before']['status'], item['movements'][0]['after']['status']))
        for note in coaching_outcomes.LIMITATIONS:
            self.assertIn(note, report['limitations'])
        json.dumps(report, allow_nan=False)

    def test_an_unstarted_draft_is_reported_as_such(self):
        self.save()
        item = coaching.build_report(self.db, today=DAY)['proposal_outcomes'][0]
        self.assertEqual(('not_started', 'not_executed'), (item['stage'], item['comparison']))

    def test_no_proposals_means_an_empty_list(self):
        self.assertEqual([], coaching.build_report(self.db, today=DAY)['proposal_outcomes'])

    def test_a_database_without_the_proposals_table_is_not_an_incomplete_read(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('DROP TABLE plan_proposals')
            conn.commit()
        report = coaching.build_report(self.db, today=DAY)
        self.assertEqual('available', report['coverage']['local_source'])
        self.assertEqual([], report['proposal_outcomes'])

    def test_other_database_failures_still_mark_the_read_incomplete(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('DROP TABLE plan_proposals')
            conn.execute('CREATE TABLE plan_proposals (id TEXT)')  # exists but unreadable as expected
            conn.commit()
        report = coaching.build_report(self.db, today=DAY)
        self.assertEqual('unavailable_or_incomplete', report['coverage']['local_source'])
        self.assertEqual([], report['proposal_outcomes'])

    def test_brief_frames_outcomes_as_history_not_proof(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('proposal_outcomes', 'Use it to calibrate, not to grade yourself',
                       'no outcome shows that a proposal caused a change',
                       'never say a proposal was applied or a change was made'):
            self.assertIn(phrase, brief)

    def test_context_trimming_drops_old_outcomes_before_failing(self):
        for i in range(3):
            self.save(identity=f'a{i}', saved=f'2026-09-2{i}T10:00:00+00:00', plan_id=f'p{i}')
        full = coaching.build_report(self.db, today=DAY)
        self.assertEqual(3, len(full['proposal_outcomes']))
        trimmed = None
        for limit in range(len(coaching.encode(full)), 0, -60):
            try:
                candidate = coaching.build_report(self.db, today=DAY, context_limit=limit)
            except ValueError:
                break
            if any('proposal_outcomes: older detail omitted' in note for note in candidate['limitations']):
                trimmed = candidate
                break
        self.assertIsNotNone(trimmed)
        self.assertLess(len(trimmed['proposal_outcomes']), 3)
        self.assertEqual('a2', trimmed['proposal_outcomes'][0]['proposal_id'])  # newest is kept longest
