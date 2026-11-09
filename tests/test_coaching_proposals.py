"""Coach side of plan proposals: the format it is told to use and the movements it may name."""
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
from database import Base, WorkoutLog, WorkoutSession
from rackbook import database as logger
from rackbook import plan_changes, plan_proposals

DAY = date(2026, 11, 5)


class BriefTests(TestCase):
    def test_example_matches_the_parser_shape_and_fence(self):
        example = json.loads(coaching.PROPOSAL_EXAMPLE)
        self.assertEqual(plan_proposals.FENCE, example['version'])
        parsed = plan_proposals.Proposal.model_validate(example)
        self.assertEqual(1, len(parsed.sessions))
        self.assertIn('```' + plan_proposals.FENCE, coaching.BRIEF)
        self.assertIn(coaching.PROPOSAL_EXAMPLE, coaching.BRIEF)

    def test_the_brief_example_is_found_by_the_parser_fence(self):
        blocks = plan_proposals.BLOCK.findall(coaching.BRIEF)
        self.assertEqual([coaching.PROPOSAL_EXAMPLE], [b.strip() for b in blocks])

    def test_brief_limits_what_a_proposal_may_do(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('Only when the athlete asks for a concrete training week or plan',
                       'Use only exercise_template_id values listed in known_movements or the live exercise_library',
                       'Never include weights', 'inactive draft', 'never say a change has been made',
                       'Omit the block when you are only discussing'):
            self.assertIn(phrase, brief)
        self.assertIn('you never apply them yourself', brief)
        self.assertIn("Only the athlete's own tap applies a plan change", brief)

    def test_brief_explains_the_weekly_coaching_call(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('A weekly coaching call (week_context.kind call) replaces both',
                       'give the next week as one plan-proposal block', 'give changes to it as one plan-change block',
                       'Keeping everything the same is a good answer', 'build that program only after they agree',
                       'Run it back to repeat the finished week unchanged',
                       'Outside a weekly coaching call the athlete can preview it and save it only as an inactive draft'):
            self.assertIn(phrase, brief)

    def test_plan_change_example_matches_the_change_parser(self):
        example = json.loads(coaching.PLAN_CHANGE_EXAMPLE)
        self.assertEqual(plan_changes.FENCE, example['version'])
        parsed = plan_changes.PlanChange.model_validate(example)
        self.assertEqual(['set_sets', 'replace'], [c.op for c in parsed.changes])
        blocks = plan_changes.BLOCK.findall(coaching.BRIEF)
        self.assertEqual([coaching.PLAN_CHANGE_EXAMPLE], [b.strip() for b in blocks])

    def test_brief_limits_what_a_plan_change_may_do(self):
        brief = ' '.join(coaching.BRIEF.split())
        for phrase in ('When the athlete asks to change an existing plan', 'Take plan_id and revision from the live current_plans',
                       'Change only days whose status is pending', 'trained and skipped days can never change',
                       'never include weights', 'applies it only with their own tap', 'never say it has been applied',
                       'If the live state is unavailable, describe the change in words and omit the block',
                       'Holding the plan unchanged is a valid answer',
                       'do not repeat it unless the training shows something new'):
            self.assertIn(phrase, brief)


class KnownMovementTests(TestCase):
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

    def imported(self, identity, days_ago, exercise_id, title):
        day = DAY - timedelta(days=days_ago)
        self.db.add(WorkoutSession(hevy_workout_id=identity, workout_date=day, workout_title='Strength',
                                   start_time=datetime(day.year, day.month, day.day, 17)))
        self.db.add(WorkoutLog(workout_id=identity, date=day, exercise_id=exercise_id, exercise_title=title,
                               set_number=1, weight_lbs=220, reps=5, rpe=8))
        self.db.commit()

    def test_known_movements_cover_history_and_saved_plans_but_not_unidentified_exercises(self):
        self.imported('a', 10, 'sq', 'Squat')
        self.imported('b', 3, 'sq', 'Squat')
        self.imported('c', 5, 'bp', 'Bench Press')
        self.imported('d', 2, None, 'Mystery lift')
        document = dict(name='Plan', weeks=[dict(name='Week 1', sessions=[dict(id='d1', name='Day', exercises=[
            dict(exercise_template_id='row', title='Row', sets=[dict(reps=5)]),
            dict(exercise_template_id='bp', title='Bench Press', sets=[dict(reps=5)])])])])
        with logger.get_db() as conn:
            conn.execute('INSERT INTO mesocycles (id, document, active) VALUES (?, ?, 1)', ('p', json.dumps(document)))
        report = coaching.build_report(self.db, today=DAY)
        known = {m['exercise_template_id']: m for m in report['known_movements']}
        self.assertEqual({'sq', 'bp', 'row'}, set(known))
        self.assertEqual(dict(title='Squat', last_date=str(DAY - timedelta(days=3)), exposure_count=2, in_saved_plan=False,
                              exercise_template_id='sq'), known['sq'])
        self.assertTrue(known['bp']['in_saved_plan'])
        self.assertEqual((None, 0, 'Row'), (known['row']['last_date'], known['row']['exposure_count'], known['row']['title']))
        self.assertEqual(['sq', 'bp', 'row'], [m['exercise_template_id'] for m in report['known_movements']])  # most recent first
        self.assertTrue(any('known_movements' in note for note in report['limitations']))
        json.dumps(report, allow_nan=False)

    def test_known_movements_are_capped(self):
        for index in range(3):
            self.imported(str(index), index + 1, f'id{index}', f'Lift {index}')
        with patch.object(coaching, 'KNOWN_MOVEMENTS', 2):
            report = coaching.build_report(self.db, today=DAY)
        self.assertEqual(['id0', 'id1'], [m['exercise_template_id'] for m in report['known_movements']])

    def test_every_listed_movement_is_accepted_by_the_preview_validator(self):
        self.imported('a', 3, 'sq', 'Squat')
        known = coaching.build_report(self.db, today=DAY)['known_movements']
        with logger.get_db() as conn:
            conn.execute('INSERT INTO hevy_exercise_cache (id, title) VALUES (?, ?)', ('sq', 'Squat'))
        body = dict(version=plan_proposals.FENCE, title='T', rationale='R', sessions=[dict(name='A', exercises=[
            dict(exercise_template_id=known[0]['exercise_template_id'], sets=[dict(reps=5, rpe=7)])])])
        result = plan_proposals.preview('```plan-proposal-v1\n' + json.dumps(body) + '\n```')
        self.assertTrue(result['valid'], result)


class LivePlanningTests(TestCase):
    """The coach reads current plans per message so a plan change targets the plan as it stands (ADR 0002)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'logging.db'
        self.env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(self.path))
        self.env.start()
        logger.init_db()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def plan(self, identity, sessions, active=0, archived=0, revision=1):
        document = dict(name='Plan ' + identity, weeks=[dict(name='Week 1', sessions=sessions)])
        with logger.get_db() as conn:
            conn.execute('INSERT INTO mesocycles (id, document, active, archived, revision) VALUES (?, ?, ?, ?, ?)',
                         (identity, json.dumps(document), active, archived, revision))

    @staticmethod
    def day(identity, *exercises):
        return dict(id=identity, name='Day ' + identity, exercises=[
            dict(exercise_template_id=e, title=e.title(), sets=[dict(reps=5, rpe=8, weight_kg=100, ts=True, type='normal'),
                                                                dict(reps=8, rpe=None, weight_kg=None, ts=False, type='failure')])
            for e in exercises])

    def test_current_plans_show_revision_day_status_and_no_weight_values(self):
        self.plan('active', [self.day('a1', 'squat'), self.day('a2', 'bench'), self.day('a3', 'row')], active=1, revision=4)
        self.plan('draft', [self.day('b1', 'squat')])
        self.plan('done', [self.day('c1', 'squat')])
        self.plan('gone', [self.day('d1', 'squat')], archived=1)
        with logger.get_db() as conn:
            conn.executemany('INSERT INTO mesocycle_completions (mesocycle_id, session_id, hevy_workout_id, workout_start, outcome) '
                             'VALUES (?, ?, ?, ?, ?)',
                             [('active', 'a1', 'w1', '2026-11-03T10:00:00Z', 'completed'),
                              ('active', 'a2', None, '2026-11-04T10:00:00Z', 'skipped'),
                              ('done', 'c1', 'w0', '2026-10-01T10:00:00Z', 'completed')])
            conn.executemany('INSERT INTO hevy_exercise_cache (id, title) VALUES (?, ?)', [('zz', 'Zercher Squat'), ('aa', 'Ab Wheel')])
        live = coaching.live_planning('conversation-1')
        self.assertEqual('available', live['status'])
        self.assertEqual(['active', 'draft'], [p['plan_id'] for p in live['current_plans']])
        active = live['current_plans'][0]
        self.assertEqual((4, True), (active['revision'], active['active']))
        self.assertEqual([(1, 'trained'), (2, 'skipped'), (3, 'pending')], [(d['day'], d['status']) for d in active['days']])
        self.assertEqual([dict(reps=5, rpe=8, ts=True, fixed_weight=True), dict(reps=8, rpe=None, type='failure')],
                         active['days'][2]['exercises'][0]['sets'])
        self.assertNotIn('weight_kg', json.dumps(live))
        self.assertEqual([['aa', 'Ab Wheel'], ['zz', 'Zercher Squat']], live['exercise_library'])

    def test_only_this_conversations_accepted_changes_are_listed(self):
        self.plan('p', [self.day('a1', 'squat')])
        rows = [('mine', 'Swap rows', '2026-11-04T00:00:00Z', None),
                ('mine', 'Drop a set', '2026-11-04T01:00:00Z', '2026-11-05T00:00:00Z'),
                ('other', 'Other', '2026-11-04T02:00:00Z', None)]
        with logger.get_db() as conn:
            for conversation, title, applied, undone in rows:
                conn.execute('INSERT INTO plan_changes (id, conversation_id, turn_id, plan_id, title, base_revision, applied_revision, '
                             'previous_document, proposed, summary, touched, applied_at, undone_at) '
                             "VALUES (?, ?, ?, 'p', ?, 1, 2, '{}', '{}', '{}', '[]', ?, ?)",
                             (title, conversation, title, title, applied, undone))
        changes = coaching.live_planning('mine')['plan_changes']
        self.assertEqual([('Swap rows', None), ('Drop a set', '2026-11-05T00:00:00Z')],
                         [(c['title'], c['undone_at']) for c in changes])

    def test_a_missing_logging_database_is_reported_not_guessed(self):
        self.path.unlink()
        live = coaching.live_planning('x')
        self.assertEqual('unavailable_or_incomplete', live['status'])
        self.assertEqual(([], []), (live['current_plans'], live['exercise_library']))

    def test_messages_add_the_live_state_after_the_frozen_report_but_not_to_daily_recommendations(self):
        view = dict(evidence=dict(version='training-review-v1'), turns=[])
        live = dict(status='available', current_plans=[dict(plan_id='p', revision=3)])
        system = coaching.messages(view, 'Swap my rows', live=live)[0]['content']
        self.assertLess(system.index('FROZEN TRAINING REPORT'), system.index('LIVE PLANNING STATE'))
        self.assertIn('"revision":3', system)
        self.assertNotIn('LIVE PLANNING STATE', coaching.messages(view, 'Swap my rows')[0]['content'])
        daily = dict(evidence=dict(version=coaching.DAILY_RECOMMENDATION_VERSION), turns=[])
        self.assertNotIn('LIVE PLANNING STATE', coaching.messages(daily, 'Today', live=live)[0]['content'])
